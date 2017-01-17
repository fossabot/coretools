import pytest
from iotile.core.hw.hwmanager import HardwareManager
import time

def pytest_addoption(parser):
    parser.addoption('--port', default="bled112", help="Port to use to connect to iotile device")
    parser.addoption('--uuid', action="append", default=[], help="Device UUIDs to run tests on")

def pytest_generate_tests(metafunc):
    if 'port' in metafunc.fixturenames:
        port = metafunc.config.option.port

        metafunc.parametrize("port", [port], scope='session')

    if 'device_id' in metafunc.fixturenames:
        ids = [int(x, 0) for x in metafunc.config.option.uuid]
        metafunc.parametrize("device_id", ids, scope='session')

@pytest.fixture(scope='session')
def device(port, device_id):
    """Return a HardwareManager instance connected to an IOTile Device
    """
    with HardwareManager(port=port) as hw:
        time.sleep(1)

        hw.connect(device_id)
        yield hw
        hw.disconnect()

