from setuptools import setup, find_packages

setup(
    name="queuectl",
    version="0.1",
    packages=find_packages(),
    install_requires=["click", "sqlalchemy"],
    entry_points={"console_scripts": ["queuectl = flam.cli:cli"]},
)
