from setuptools import setup, find_packages

setup(
    name="directory-cleaner",
    version="1.0.0",
    description="A utility for efficiently cleaning and managing directories",
    author="Directory Cleaner Team",
    author_email="info@directory-cleaner.org",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "PyQt5>=5.15.0",
        "send2trash>=1.5.0",
        "tqdm>=4.45.0",
    ],
    entry_points={
        "console_scripts": [
            "directory-cleaner=directory_cleaner.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
)