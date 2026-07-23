import app as app_module

client = app_module.app.test_client()
with client.session_transaction() as s:
    s['username'] = 'admin'
    s['role'] = 'admin'

resp = client.get('/profile')
print('status', resp.status_code)
print('location', resp.headers.get('Location'))
print(resp.get_data(as_text=True)[:4000])
