import pdb

import os
import pytest
from iotile.sg.exceptions import SensorGraphSyntaxError, StreamEmptyError
from iotile.sg import DataStream, DeviceModel, DataStreamSelector, SlotIdentifier
from iotile.sg.parser import SensorGraphFileParser
from iotile.sg.sim import SensorGraphSimulator
import iotile.sg.parser.language as language
from iotile.core.hw.reports import IOTileReading


@pytest.fixture
def parser():
    return SensorGraphFileParser()


def get_path(name):
    return os.path.join(os.path.dirname(__file__), 'sensor_graphs', name)


def test_every_block_compilation(parser):
    """Make sure we can compile a simple every block."""

    parser.parse_file(get_path(u'basic_every_1min.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    assert len(sg.nodes) == 5

    sg.load_constants()
    # Now make sure it produces the right output
    counter15 = log.create_walker(DataStreamSelector.FromString('counter 15'))
    counter16 = log.create_walker(DataStreamSelector.FromString('counter 16'))

    sim = SensorGraphSimulator()
    sim.stop_condition('run_time 120 seconds')
    sim.run(sg)

    assert counter15.count() == 2
    assert counter16.count() == 2


def test_every_block_with_buffering(parser):
    """Make sure we can compile and simulate an every block with buffered data."""

    parser.parse_file(get_path(u'basic_output.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    assert len(sg.nodes) == 5

    sg.load_constants()
    # Now make sure it produces the right output
    output1 = log.create_walker(DataStreamSelector.FromString('output 1'))
    buffered1 = log.create_walker(DataStreamSelector.FromString('buffered 1'))

    sim = SensorGraphSimulator()
    sim.stop_condition('run_time 120 seconds')
    sim.run(sg)

    assert output1.count() == 12
    assert buffered1.count() == 12


def test_streamers(parser):
    """Make sure we can compile streamer statements."""

    parser.parse_file(get_path(u'basic_streamer.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    streamers = parser.sensor_graph.streamers
    assert len(streamers) == 2
    assert streamers[0].dest == SlotIdentifier.FromString('controller')
    assert streamers[1].dest == SlotIdentifier.FromString('slot 1')
    assert streamers[1].with_other == 0



def test_every_block_splitting(parser):
    """Make sure we can split nodes in an every block."""

    parser.parse_file(get_path(u'basic_every_split.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    assert len(sg.nodes) == 8

    # Now make sure it produces the right output
    counter15 = log.create_walker(DataStreamSelector.FromString('counter 15'))
    counter16 = log.create_walker(DataStreamSelector.FromString('counter 16'))
    counter17 = log.create_walker(DataStreamSelector.FromString('counter 16'))
    counter18 = log.create_walker(DataStreamSelector.FromString('counter 16'))

    sg.load_constants()

    sim = SensorGraphSimulator()
    sim.stop_condition('run_time 120 seconds')
    sim.run(sg)

    sg.load_constants()

    print([str(x) for x in log._last_values.keys()])

    assert counter15.count() == 2
    assert counter16.count() == 2
    assert counter17.count() == 2
    assert counter18.count() == 2


def test_when_block_clock(parser):
    """Make sure we can compile when blocks (without identifiers)."""

    parser.parse_file(get_path(u'basic_when.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    sg.load_constants()
    assert sg.user_tick() == 1

    # Now make sure it produces the right output
    counter15 = log.create_walker(DataStreamSelector.FromString('counter 15'))
    sim = SensorGraphSimulator()
    sim.stop_condition('run_time 60 seconds')
    sim.run(sg)
    assert counter15.count() == 0

    sim.step(sg, DataStream.FromString('system input 1025'), 8)
    assert counter15.count() == 1
    counter15.skip_all()

    sim.run(sg)

    assert counter15.count() == 60

    counter15.skip_all()
    sim.step(sg, DataStream.FromString('system input 1026'), 8)
    sim.run(sg)
    assert counter15.count() == 0


def test_when_block_on_event(parser):
    """Make sure on connect and on disconnect work."""

    parser.parse_file(get_path(u'basic_when_on.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    sg.load_constants()

    sim = SensorGraphSimulator()

    # We should only get a reading in unbuffered 1 on connect and unbuffered 2 on disconnect
    with pytest.raises(StreamEmptyError):
        log.inspect_last(DataStream.FromString('unbuffered 2'))

    sim.step(sg, DataStream.FromString('system input 1025'), 8)
    assert log.inspect_last(DataStream.FromString('unbuffered 1')).value == 0

    with pytest.raises(StreamEmptyError):
        log.inspect_last(DataStream.FromString('unbuffered 2'))

    sim.step(sg, DataStream.FromString('system input 1026'), 8)
    assert log.inspect_last(DataStream.FromString('unbuffered 2')).value == 0


def test_on_block(parser):
    """Make sure on count(stream), on value(stream) and on stream work."""

    parser.parse_file(get_path(u'basic_on.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    sg.load_constants()

    counter1 = log.create_walker(DataStreamSelector.FromString('counter 1'))
    counter2 = log.create_walker(DataStreamSelector.FromString('counter 2'))
    counter3 = log.create_walker(DataStreamSelector.FromString('counter 3'))

    sim = SensorGraphSimulator()
    sim.step(sg, DataStream.FromString('input 1'), 8)

    assert counter1.count() == 0
    assert counter2.count() == 0
    assert counter3.count() == 0

    for i in range(0, 10):
        sim.step(sg, DataStream.FromString('input 1'), 5)

    assert counter1.count() == 10
    assert counter2.count() == 5
    assert counter3.count() == 5


def test_config_block(parser):
    """Make sure config blocks and statement are parsed."""

    parser.parse_file(get_path(u'basic_config.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    assert sg.get_config(SlotIdentifier.FromString('controller'), 0x2000) == (u'uint32_t', 5)
    assert sg.get_config(SlotIdentifier.FromString('slot 1'), 0x5000) == (u'uint8_t', 10)


def test_copy_statement(parser):
    """Make sure we can copy data using copy."""

    parser.parse_file(get_path(u'basic_copy.sgf'))

    model = DeviceModel()
    parser.compile(model=model)

    sg = parser.sensor_graph
    log = sg.sensor_log
    for x in sg.dump_nodes():
        print(x)

    sg.load_constants()

    output1 = log.create_walker(DataStreamSelector.FromString('output 1'))
    output2 = log.create_walker(DataStreamSelector.FromString('output 2'))
    output3 = log.create_walker(DataStreamSelector.FromString('output 3'))

    sim = SensorGraphSimulator()
    sim.stop_condition('run_time 60 seconds')
    sim.run(sg)

    assert output1.count() == 1
    assert output2.count() == 1
    assert output3.count() == 1
    val1 = output1.pop()
    val2 = output2.pop()
    val3 = output3.pop()

    assert val1.value == 0
    assert val2.value == 60
    assert val3.value == 1