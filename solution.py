import re

def fix_images_in_readme(readme_path='README.md'):
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to capture markdown image syntax: ![alt](url)
    pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    def replace_image(match):
        alt, url = match.groups()
        # If the url is already a raw GitHub link, leave it
        if url.startswith('https://github.com/user-attachments/assets/') and '?raw=true' in url:
            return match.group(0)
        # If the url is relative, prefix the GitHub assets root
        if not url.startswith(('http://', 'https://')):
            url = f'https://github.com/user-attachments/assets/{url}'
        # Ensure the raw flag is present
        if '?raw=true' not in url:
            base, _ = url.split('?', 1) if '?' in url else (url, '')
            url = f'{base}?raw=true'
        return f'![{alt}]({url})'

    new_content = pattern.sub(replace_image, content)

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == "__main__":
    fix_images_in_readme()