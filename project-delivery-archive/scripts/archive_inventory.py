#!/usr/bin/env python3
"""Read-only metadata/content inventory. Never copy, move, delete, or execute Git."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


def stable_signature(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def hash_regular(path, before, dir_fd=None):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags, dir_fd=dir_fd)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or stable_signature(opened) != stable_signature(before):
            raise OSError('File changed before reading')
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        after = os.fstat(fd)
        if size != before.st_size or stable_signature(after) != stable_signature(before):
            raise OSError('File changed while reading')
        if stable_signature(os.stat(path, dir_fd=dir_fd, follow_symlinks=False)) != stable_signature(before):
            raise OSError('Path changed while reading')
        return digest.hexdigest()
    finally:
        os.close(fd)


def inventory(root, with_hash=False):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Source must be a directory')
    if not (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
            and os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
            and os.scandir in os.supports_fd):
        raise ValueError('Safe descriptor-based traversal requires a supported POSIX platform')
    entries, errors = [], []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    def walk(folder_fd, relative, initial):
        try:
            with os.scandir(folder_fd) as iterator:
                names = sorted(entry.name for entry in iterator)
        except OSError as e:
            errors.append({'path': relative or '.', 'error': str(e)})
            return
        for name in names:
            rel = relative + '/' + name if relative else name
            row = {'path': rel}
            try:
                s = os.stat(name, dir_fd=folder_fd, follow_symlinks=False)
                row.update(size=s.st_size, mtime_ns=s.st_mtime_ns, mode=stat.S_IMODE(s.st_mode))
                if stat.S_ISLNK(s.st_mode):
                    row.update(type='symlink', target=os.readlink(name, dir_fd=folder_fd))
                elif stat.S_ISDIR(s.st_mode):
                    row['type'] = 'directory'
                    child_fd = os.open(name, flags, dir_fd=folder_fd)
                    try:
                        if stable_signature(os.fstat(child_fd)) != stable_signature(s):
                            raise OSError('Directory changed before traversal')
                        walk(child_fd, rel, s)
                        if stable_signature(os.stat(name, dir_fd=folder_fd, follow_symlinks=False)) != stable_signature(s):
                            raise OSError('Directory path changed during traversal')
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(s.st_mode):
                    row['type'] = 'file'
                    if name.endswith('.icloud'):
                        row['warning'] = 'possible_cloud_placeholder'
                    elif with_hash:
                        row['sha256'] = hash_regular(name, s, dir_fd=folder_fd)
                else:
                    row.update(type='special', warning='unsupported_special_file')
            except OSError as e:
                row['error'] = str(e)
            entries.append(row)
        try:
            if stable_signature(os.fstat(folder_fd)) != stable_signature(initial):
                raise OSError('Directory changed during traversal')
        except OSError as e:
            errors.append({'path': relative or '.', 'error': str(e)})

    root_fd = os.open(root, flags)
    try:
        initial = os.fstat(root_fd)
        walk(root_fd, '', initial)
        if stable_signature(os.stat(root, follow_symlinks=False)) != stable_signature(initial):
            errors.append({'path': '.', 'error': 'Source root changed during traversal'})
    finally:
        os.close(root_fd)
    entries.sort(key=lambda row: row['path'])
    unresolved = [e['path'] for e in entries if e.get('error') or e.get('warning')]
    regular = [e for e in entries if e.get('type') == 'file']
    complete = with_hash and not errors and not unresolved and all('sha256' in e for e in regular)
    return {
        'schema_version': 1, 'root': str(root),
        'scanned_at': datetime.now(timezone.utc).isoformat(),
        'hash_algorithm': 'sha256' if with_hash else None,
        'scope': 'relative paths, file bytes, directory entries, symlink targets; no ACL/xattrs/resource forks/hardlink validation',
        'content_inventory_complete': bool(complete),
        'regular_file_count': len(regular),
        'logical_bytes': sum(e['size'] for e in regular),
        'unresolved_paths': unresolved, 'scan_errors': errors, 'entries': entries,
    }


def compare(left, right):
    for manifest in (left, right):
        if manifest.get('schema_version') != 1:
            raise ValueError('Unsupported inventory schema')
        if not manifest.get('content_inventory_complete'):
            return {'match': False, 'reason': 'Both inventories must have complete content hashes and no unresolved paths'}
    def index(manifest):
        out = {}
        for row in manifest['entries']:
            if row['path'] in out:
                raise ValueError('Duplicate inventory path')
            out[row['path']] = row
        return out
    a, b = index(left), index(right)
    missing, extra, mismatched = sorted(a.keys()-b.keys()), sorted(b.keys()-a.keys()), []
    for path in sorted(a.keys() & b.keys()):
        x, y = a[path], b[path]
        if x['type'] != y['type']:
            mismatched.append({'path': path, 'reason': 'type'})
        elif x['type'] == 'file':
            if not x.get('sha256') or not y.get('sha256'):
                raise ValueError('Missing hash in supposedly complete inventory')
            if (x['size'], x['sha256']) != (y['size'], y['sha256']):
                mismatched.append({'path': path, 'reason': 'content'})
        elif x['type'] == 'symlink' and x['target'] != y['target']:
            mismatched.append({'path': path, 'reason': 'symlink target'})
        elif x['type'] not in ('directory', 'symlink'):
            raise ValueError('Unsupported file type')
    return {'match': not (missing or extra or mismatched), 'missing': missing, 'extra': extra,
            'mismatched': mismatched, 'scope': left['scope'],
            'recovery_verified': False, 'cleanup_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('scan')
    scan.add_argument('root', type=Path)
    scan.add_argument('--hash', action='store_true', help='Read every regular file; may trigger cloud downloads')
    scan.add_argument('--output', type=Path, required=True, help='New JSON path outside the source tree')
    diff = commands.add_parser('compare')
    diff.add_argument('source', type=Path)
    diff.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'scan':
            root = args.root.resolve(strict=True)
            output = args.output.resolve()
            if output == root or root in output.parents:
                raise ValueError('Output must be outside the source tree')
            if output.exists():
                raise ValueError('Refusing to overwrite an existing manifest')
            result = inventory(root, args.hash)
            with output.open('x', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.write('\n')
            print(json.dumps({'output': str(output), 'content_inventory_complete': result['content_inventory_complete'],
                              'regular_file_count': result['regular_file_count'], 'unresolved_paths': result['unresolved_paths']}, ensure_ascii=False))
            return 2 if result['scan_errors'] or result['unresolved_paths'] else 0
        result = compare(json.loads(args.source.read_text()), json.loads(args.archive.read_text()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['match'] else 2
    except (OSError, ValueError, KeyError, TypeError) as e:
        print('ERROR: '+str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
