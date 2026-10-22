"""Read-only API smoke check for the unified mini-program's role workspaces."""
import argparse
import json
from pathlib import Path

import httpx


ROUTES = {
    'customer': ['/me', '/catalog/products', '/wishlist', '/inquiries', '/orders', '/tickets', '/addresses', '/notifications'],
    'merchant': ['/me', '/catalog/products', '/quotes', '/admin/catalog', '/merchant/profile', '/notifications'],
    'admin': ['/me', '/admin/dashboard', '/admin/catalog', '/quotes', '/admin/merchants', '/admin/users', '/inquiries', '/orders?limit=50', '/procurements', '/tickets', '/reviews', '/settings', '/admin/index', '/admin/exceptions', '/admin/audits'],
}


def check(base_url, credentials):
    data = json.loads(Path(credentials).read_text(encoding='utf-8'))
    accounts = {a['role']: a['username'] for a in data['accounts'] if a['role'] in ROUTES}
    with httpx.Client(base_url=base_url.rstrip('/'), timeout=15) as client:
        for role, routes in ROUTES.items():
            login = client.post('/api/auth/login', json={'username': accounts[role], 'password': data['password']})
            login.raise_for_status()
            token = login.json()['token']
            for route in routes:
                response = client.get('/api' + route, headers={'Authorization': 'Bearer ' + token})
                response.raise_for_status()
                assert isinstance(response.json(), (list, dict)), (role, route)
            print(f'{role}: {len(routes)} role routes OK')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--credentials', default='local-only/demo-accounts.json')
    args = parser.parse_args()
    check(args.base_url, args.credentials)
