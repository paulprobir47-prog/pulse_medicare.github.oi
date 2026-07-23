from pathlib import Path

script = "\n<script>\n(function() {\n    if (localStorage.getItem('dashboardTheme') === 'dark') {\n        document.body.classList.add('dark');\n    }\n})();\n</script>\n"
files = [Path('templates/login.html'), Path('templates/patients.html'), Path('templates/index.html')]
for fp in files:
    text = fp.read_text(encoding='utf-8')
    if "localStorage.getItem('dashboardTheme')" in text:
        print(f'skip {fp.name} already has script')
        continue
    if '</body>\r\n</html>\r\n' in text:
        text = text.replace('</body>\r\n</html>\r\n', script + '</body>\r\n</html>\r\n')
    elif '</body>\n</html>\n' in text:
        text = text.replace('</body>\n</html>\n', script + '</body>\n</html>\n')
    elif '</body>\n</html>' in text:
        text = text.replace('</body>\n</html>', script + '</body>\n</html>')
    else:
        print(f'missing closing tags in {fp.name}')
        continue
    fp.write_text(text, encoding='utf-8')
    print(f'updated {fp.name}')
