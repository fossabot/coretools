import unittest
import os
import pytest
from iotile.core.exceptions import *
from iotile.core.hw.reports.signed_list_format import SignedListReport
from iotile.core.hw.reports.report import IOTileReading
import struct
import datetime
from copy import deepcopy

def make_sequential(iotile_id, stream, num_readings, give_ids=False, signature_method=0):
    readings = []

    for i in xrange(0, num_readings):
        if give_ids:
            reading = IOTileReading(i, stream, i, reading_id=i+1)
        else:
            reading = IOTileReading(i, stream, i)

        readings.append(reading)
        
    report = SignedListReport.FromReadings(iotile_id, readings, signature_method=signature_method)
    return report

def test_basic_parsing():
    """Make sure we can decode a signed report
    """

    report = make_sequential(1, 0x1000, 10)
    encoded = report.encode()

    report2 = SignedListReport(encoded)

    assert len(report.visible_readings) == 10
    assert len(report2.visible_readings) == 10

    for i, reading in enumerate(report.visible_readings):
        assert reading == report2.visible_readings[i]

    assert report2.verified == True
    assert report.verified == True
    assert report.signature_flags == 0

def test_footer_calculation():
    """
    """

    report1 = make_sequential(1, 0x1000, 10, give_ids=False)
    report2 = make_sequential(1, 0x1000, 10, give_ids=True)

    assert report1.lowest_id == 0
    assert report1.highest_id == 0

    assert report2.lowest_id == 1
    assert report2.highest_id == 10

def test_userkey_signing(monkeypatch):
    print(os.environ.keys())
    monkeypatch.setenv('USER_KEY_00000002', '0000000000000000000000000000000000000000000000000000000000000000')

    with pytest.raises(EnvironmentError):
        report1 = make_sequential(1, 0x1000, 10, give_ids=True, signature_method=1)

    report1 = make_sequential(2, 0x1000, 10, give_ids=True, signature_method=1)

    encoded = report1.encode()
    report2 = SignedListReport(encoded)

    assert report1.signature_flags == 1
    assert report2.signature_flags == 1
    assert report1.verified
    assert report2.verified