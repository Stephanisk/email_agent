from setuptools import setup, find_packages

setup(
    name="mailagent",
    version="0.1",
    packages=find_packages(include=['app', 'app.*']),
    python_requires=">=3.8",
    install_requires=[
        "fastapi",
        "python-dotenv",
        "pydantic-settings",
        "python-imap4",
        "email-validator",
        "aiofiles",
    ],
    author="Your Name",
    description="Email agent for hostel management",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
) 