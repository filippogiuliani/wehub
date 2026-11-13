"""Server administration commands.

  python manage.py new-key        a random key for an app (put it in WEHUB_APP_<APP>_KEY and in the app's *_HUB_KEY)
  python manage.py backup         database backup now
  python manage.py backups        list backups
  python manage.py users          users and families
"""
import secrets
import sys

from famkit import backup
import db


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ''
    if cmd == 'new-key':
        print(secrets.token_urlsafe(32))
    elif cmd == 'backup':
        print('Created:', backup.create_backup('manual'))
    elif cmd == 'backups':
        for b in backup.list_backups():
            print(f"{b['created_at']}  {b['size'] // 1024:>6} KB  {b['name']}")
    elif cmd == 'users':
        conn = db.connect()
        for r in conn.execute('''SELECT u.email, u.name, f.name AS family, m.role FROM users u
                                 LEFT JOIN members m ON m.user_id = u.id LEFT JOIN families f ON f.id = m.family_id ORDER BY f.id'''):
            print(f"{r['email']:<35} {r['name']:<20} {r['family'] or '-'} ({r['role'] or '-'})")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
