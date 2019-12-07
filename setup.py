from setuptools import setup, find_packages


with open('README.md') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='ForumMediaScraperREST',
    version='0.1.0',
    description='REST interface to interact with ForumMediaScraper app',
    long_description=readme,
    author='Jesse van der Wolf',
    author_email='j3ss3hop@yahoo.nl',
    url='https://github.com/jesseVDwolf/ForumMediaScraperREST',
    license=license,
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,
    zip_safe=False
)