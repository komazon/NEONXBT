from setuptools import setup

setup(
    name="NEO_NXBT",
    include_package_data=True,
    long_description_content_type="text/markdown",
    install_requires=[
        "dbus-python==1.2.16",
        "fastapi>=0.104.0",
        "python-socketio>=5.9.0",
        "uvicorn[standard]>=0.24.0",
        "blessed==1.17.10",
        "pynput==1.7.1",
        "psutil==5.6.6",
        "cryptography>=41.0.0",
    ],
    extras_require={
        "dev": [
            "pytest"
        ]
    }
)
