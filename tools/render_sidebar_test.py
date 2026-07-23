import os
import sys
import traceback

# ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from app import app

with app.test_request_context('/', method='GET'):
    try:
        tpl = app.jinja_env.get_or_select_template('_sidebar.html')
        html = tpl.render(username='testuser', sections=[], active_section={'slug':'test','label':'Test'}, items=[], request=app.test_request_context().request, session={'username':'testuser'})
        print('rendered length', len(html))
    except Exception:
        traceback.print_exc()
