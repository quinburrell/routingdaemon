from configparser import ConfigParser
import re
import sys
import time
import select
import socket

"""
Authors: Quin Burrell and Alex McCarty
Date:    21 March 2021
Purpose: Parses router.ini files and does basic error checks

TODO:
build_packet method
update routing table func
hello packet protocols
"""


class RipEntry:
    """An object that represents all the information about the router for an RIP Entry"""
    def __init__(self, router_id, inputs, outputs, timer_start, metric):
        self.router_id = router_id
        self.inputs = inputs
        self.outputs = outputs
        self.timer_start = timer_start
        self.metric = metric

    def build_packet(self):
        return ([0] * 7) + [self.router_id] + ([0] * 11) + [1]


def error_msg(error_code):
    """Returns an error message associated with the number error_code"""
    error_text = {
        0: "Please enter a value between 1 and 64000",
        1: "Your input ports do not match your output ports. Please update your configuration file",
        2: "Please make sure you do not have the same entry in your input and output port fields",
        3: "Please make sure your port numbers are between 1024 and 64000",
        4: "Failed to initialise sockets",
        10: "Packet contains less than one RIP Entry",
        11: "RIP Packet header incorrect",
        12: "Packet contains fragments"
    }
    return error_text[error_code]


def read_config(file):
    """reads a .ini file intended as a config file for a router. If the .ini file has the expected format and
    information an RIP entry is created with the router id, and lists of the input and output port numbers."""
    config = ConfigParser()  # Creates an instance of the config parser
    config.read(file)  # Config parser reads the given router file

    # Router ID
    router_num = int(config['router']['router_id'])  # Extracts router id from config file
    if 1 >= router_num >= 64000:  # Checks id is a valid id
        sys.exit(error_msg(0))  # Error

    # Input ports
    inputs = config['router']['input_ports'].split(', ')  # Extracts input ports from config file
    input_ports = []
    neighbours = []

    for entry in inputs:
        entry = int(entry)
        if 1024 < entry < 64000:  # Checks input port is valid
            input_ports.append(entry)  # If valid, appends to list fo input ports
            neighbours.append(int((entry - (router_num * 1000))/100))  # Finds the router id of the neighbouring router
        else:

            sys.exit(error_msg(0))  # Error

    # Outputs
    out = config['router']['outputs'].split(', ')  # Extracts outputs from the config file
    output_ports = []

    for entry in out:
        re_result = re.search("(.*)-(.)-(.)", entry).groups()  # Uses a regex to split the values of the entry
        output_port, metric, router_id = [int(i) for i in re_result]  # Changes all values to ints
        if 1024 <= output_port <= 64000:  # Checks port number is valid
            if output_port not in input_ports:  # Checks this port number is not also an input port
                if router_id in neighbours:  # Checks that the output port has a matching input port for that router
                    output_ports.append([output_port, metric, router_id])
                else:
                    sys.exit(error_msg(1))  # Error
            else:
                sys.exit(error_msg(2))  # Error
        else:
            sys.exit(error_msg(3))  # Error

    start = time.time()
    return RipEntry(router_num, input_ports, output_ports, start, 0)


def rip_packet(rip_entries):
    """taking a list of the entries in an rip table, builds a byte array to send as a packet"""
    packet = bytearray([2, 2, 0, 0])    # The RIP header
    for entry in rip_entries:
        packet += bytearray(entry.build_packet())  # a bytearray representing each RIP Entry
    return packet  # returns the entire packet as a bytearray


def init_sockets(inputs):
    sockets = []  # a list of the sockets available
    try:
        for i in range(len(inputs)):
            sockets += [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]  # opens a sockets for each supplied input
        for i, sock in enumerate(sockets):
            sock.bind(('localhost', inputs[i]))
            print("socket on port", inputs[i], "initialised")
    except socket.error:
        sys.exit(error_msg(4))  # Error. Socket could not be bound.
    return sockets


def format_check(rec_packet):
    """Returns True if the received packet is formated correctly, otherwise provides an error message and False"""
    if len(rec_packet) < 4:  # packet contains at least one RIP entry
        error_msg(10)
    elif rec_packet[0:5] != b'\2\2\0\0':  # Packet header is correct
        error_msg(11)
    elif (len(rec_packet)-4) % 20 != 0:
        error_msg(12)
    else:
        return True
    return False


def update_table(rec_packet, routing_table, i=3):
    """updates routing table to be in accordance with the received packet"""
    while i < len(rec_packet):
        new = RipEntry(rec_packet[i+8], [], [], 0, rec_packet[i+20]+1)
        routing_table += [new]
        i += 20
    return routing_table


def mainloop():
    """mainloop of the program"""
    filename = sys.argv[1]  # Holds the variable given in the command line
    routing_table = [read_config(filename)]  # A list of RipEntry obj, one for each router that this router is aware of
    sockets = init_sockets(routing_table[0].inputs)  # A list of sockets that this router is neighbouring
    # The router informs its neighbours of its own existence
    for i, sock in enumerate(sockets):
        sock.sendto(rip_packet(routing_table), ('localhost', routing_table[0].inputs[i]))
    while 1:
        for entry in routing_table:
            print(entry.build_packet())
        # The router then waits for updates
        readable, _, _ = select.select(sockets, [], [])
        for read in readable:
            data, sender_addr = read.recvfrom(1024)
            print("packet received from", sender_addr)
            # Router checks the new packet format and if it is different from current routing table
            if format_check(data):
                if routing_table.build_packet() != data:
                    # Router updates its routing table and informs its neighbours of the change
                    routing_table = update_table(data, routing_table)
                    for sock in sockets:
                        sock.sendto(rip_packet(routing_table))


mainloop()
