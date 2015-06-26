from pymomo.commander.exceptions import *
from pymomo.exceptions import HardwareError
from cmdstream import CMDStream
from pymomo.commander.commands import RPCCommand

class FSUStream (CMDStream):
	"""
	Send command frames over a transport layer and receive the response
	This converts a byte oriented stream to a frame oriented one.  It works with the 
	current FSU implementation.
	"""

	#Types of frame markers
	ACK = 0x06
	NACK = 0x15
	term_chars = [ACK, NACK]

	OkayResult = 0
	ErrorResult = 1

	def __init__(self, transport):
		self.trans = transport

	def parse_term(self, char):
		term = ord(char)

		if term == CMDStream.ACK:
			result = CMDStream.OkayResult
		elif term == CMDStream.NACK:
			result = CMDStream.ErrorResult
		else:
			raise HardwareError("Invalid terminator character encountered", stream_type="Field Service Unit", terminator=term)

		return result

	def read_frame(self):
		buffer, tchar = self.trans.read_until(CMDStream.term_chars)
		return buffer, self.parse_term(tchar)

	def _handle_rpc_result(self):
		"""
		Handle the RPC command result
		"""
		complete_status = ord(self.trans.read())
		status = complete_status & 0b00111111

		if complete_status == 254:
			buf, term = self.read_frame()
			raise StreamNotConnectedError(stream_type="Field Service Unit")

		result = []
		#Only read data if the command was successful and the module did not return busy
		if status == 0 and status_value != 0:
			num_bytes = ord(self.trans.read())

			buf = self.trans.read(num_bytes)
			result = buf

		seq = self.trans.read()
		self.status = status

		self.parse_term(seq)
		return complete_status, result

	#Supported Stream Commands
	def _send_rpc(self, address, feature, command, *args):
		rpc = RPCCommand(address, feature, command, *args)
		cmd = str(rpc)

		if cmd[-1] != '\n':
			cmd += '\n'

		#Write the command and read the response
		self.trans.write(cmd)
		status, payload = self._handle_rpc_result()
		
		return status, payload

	def _heartbeat(self):
		"""
		Send a heartbeat character on the line that the FSU should respond to with
		the same character if it is working correctly.  Return true if the heartbeat
		was received, return false otherwise.
		"""

		self.trans.write(chr(255))
		
		c = self.trans.read()
		if len(c) == 0 or c[0] != chr(255):
			return False 

		return True

	def _reset(self):
		self.trans.write(chr(0))
		c = self.trans.read()
		if len(c) == 0 or c[0] != chr(1):
			return False 

		return True
