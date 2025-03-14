from setuptools import find_packages, setup

setup(
    name="peerless_lib",
    version="0.1.0",
    description="Provides common functionality and utilities that can be reused across different Peerless applications.",
    author="wrath",
    author_email="wrath.business0@gmail.com",
    url="https://github.com/vxWrath/peerless-lib",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "asyncpg",
        "redis[hiredis]",
        "discord.py",
        "pydantic",
        "colorlog",
    ],
    python_requires=">=3.13",
)
