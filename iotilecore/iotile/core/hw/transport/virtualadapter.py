import pkg_resources
import json
import traceback
from adapter import DeviceAdapter
from iotile.core.exceptions import ArgumentError
from iotile.core.hw.virtual.virtualdevice import RPCInvalidIDError, TileNotFoundError, RPCNotFoundError

class VirtualDeviceAdapter(DeviceAdapter):
    """Callback based adapter that gives access to one or more virtual devices
    
    The adapter is created and serves access to the virtual_devices that are
    found by name in the entry_point group iotile.virtual_device.

    Args:
        port (string): A port description that should be in the form of
            device_name1@<optional_config_json1;device_name2@optional_config_json2
    """

    def __init__(self, port):
        super(VirtualDeviceAdapter, self).__init__()

        devs = port.split(';')
        loaded_devs = {}

        for dev in devs:
            name, sep, config = dev.partition('@')

            if len(config) == 0:
                config = None

            loaded_dev = self._load_device(name, config)
            loaded_devs[loaded_dev.iotile_id] = loaded_dev

        self.devices = loaded_devs
        self.connections = {}

    def _load_device(self, name, config):
        if config is None:
            config_dict = {}
        else:
            with open(config, "rb") as conf:
                data = json.load(conf)

            if 'device' not in data:
                raise ArgumentError("Invalid configuration file passed to VirtualDeviceAdapter", device_name=name, config_path=config, missing_key='device')

            config_dict = data['device']

        seen_names = []
        for entry in pkg_resources.iter_entry_points('iotile.virtual_device'):
            if entry.name == name:
                device_factory = entry.load()
                return device_factory(config_dict)

            seen_names.append(entry.name)

        raise ArgumentError("Could not find virtual_device by name", name=name, known_names=seen_names)

    def connect_async(self, connection_id, connection_string, callback):
        """Asynchronously connect to a device

        Args:
            connection_id (int): A unique identifer that will refer to this connection
            connection_string (string): A DeviceAdapter specific string that can be used to connect to
                a device using this DeviceAdapter.
            callback (callable): A function that will be called when the connection attempt finishes as
                callback(conection_id, adapter_id, success: bool, failure_reason: string or None)
        """

        id_number = int(connection_string)
        if id_number not in self.devices:
            if callback is not None:
                callback(connection_id, self.id, False, "could not find device to connect to")
            return
        
        if id_number in [x.iotile_id for x in self.connections.itervalues()]:
            if callback is not None:
                callback(connection_id, self.id, False, "device was already connected to")
            return

        dev = self.devices[id_number]

        self.connections[connection_id] = dev

        if callback is not None:
            callback(connection_id, self.id, True, "")

    def disconnect_async(self, conn_id, callback):
        """Asynchronously disconnect from a connected device

        Args:
            conn_id (int): A unique identifer that will refer to this connection
            callback (callback): A callback that will be called as
                callback(conn_id, adapter_id, success, failure_reason)
        """

        if conn_id not in self.connections:
            if callback is not None:
                callback(conn_id, self.id, False, "device had no active connection")
            return

        dev = self.connections[conn_id]
        del self.connections[conn_id]

        if callback is not None:
            callback(conn_id, self.id, True, "")

    def _open_rpc_interface(self, conn_id, callback):
        """Open the RPC interface on a device

        Args:
            conn_id (int): A unique identifer that will refer to this connection
            callback (callback): A callback that will be called as
                callback(conn_id, adapter_id, success, failure_reason)
        """

        if conn_id not in self.connections:
            if callback is not None:
                callback(conn_id, self.id, False, "device had no active connection")
            return

        dev = self.connections[conn_id]
        dev.open_rpc_interface()

        if callback is not None:
            callback(conn_id, self.id, True, "")

    def _open_streaming_interface(self, conn_id, callback):
        """Open the streaming interface on a device

        Args:
            conn_id (int): A unique identifer that will refer to this connection
            callback (callback): A callback that will be called as
                callback(conn_id, adapter_id, success, failure_reason)
        """

        if conn_id not in self.connections:
            if callback is not None:
                callback(conn_id, self.id, False, "device had no active connection")
            return

        dev = self.connections[conn_id]
        reports = dev.open_streaming_interface()

        if callback is not None:
            callback(conn_id, self.id, True, "")
        
        for report in reports:
            self._trigger_callback('on_report', conn_id, report)

    def _open_script_interface(self, conn_id, callback):
        """Open the script interface on a device

        Args:
            conn_id (int): A unique identifer that will refer to this connection
            callback (callback): A callback that will be called as
                callback(conn_id, adapter_id, success, failure_reason)
        """

        if conn_id not in self.connections:
            if callback is not None:
                callback(conn_id, self.id, False, "device had no active connection")
            return

        dev = self.connections[conn_id]
        dev.open_script_interface()

        if callback is not None:
            callback(conn_id, self.id, True, "")

    def send_rpc_async(self, conn_id, address, rpc_id, payload, timeout, callback):
        """Asynchronously send an RPC to this IOTile device

        Args:
            conn_id (int): A unique identifer that will refer to this connection
            address (int): the addres of the tile that we wish to send the RPC to
            rpc_id (int): the 16-bit id of the RPC we want to call
            payload (bytearray): the payload of the command
            timeout (float): the number of seconds to wait for the RPC to execute
            callback (callable): A callback for when we have finished the RPC.  The callback will be called as" 
                callback(connection_id, adapter_id, success, failure_reason, status, payload)
                'connection_id': the connection id
                'adapter_id': this adapter's id
                'success': a bool indicating whether we received a response to our attempted RPC
                'failure_reason': a string with the reason for the failure if success == False
                'status': the one byte status code returned for the RPC if success == True else None
                'payload': a bytearray with the payload returned by RPC if success == True else None
        """

        if conn_id not in self.connections:
            if callback is not None:
                callback(conn_id, self.id, False, 'Device is not in connected state', None, None)
            return

        dev = self.connections[conn_id]

        status = (1 << 6)
        try:
            response = dev.call_rpc(address, rpc_id, str(payload))
            if len(response) > 0:
                status |= (1 << 7)
        except (RPCInvalidIDError, RPCNotFoundError):
            status = 2
            response = ""
        except TileNotFoundError:
            status = 0xFF
            response = ""
        except Exception:
            #Don't allow exceptions or we will deadlock
            status = 3
            response = ""

            print("*** EXCEPTION OCCURRED IN RPC ***")
            traceback.print_exc()
            print("*** END EXCEPTION ***")

        response = bytearray(response)
        callback(conn_id, self.id, True, "", status, response)

    def periodic_callback(self):
        pass

    def stop_sync(self):
        pass