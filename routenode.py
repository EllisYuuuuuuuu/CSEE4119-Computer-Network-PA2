import random
import socket
import sys
import threading
import time
from socket import *
from time import *

BUFFER = 2048
ROUTING_INTERVAL = 30
HEAD1 = "1"  # routing table change
HEAD2 = "2"  # link cost change

node_port = None
init_neighbors = {}

dv = {}
next_hop = {}
send_count = 0

other_ports_lsa = {}
all_edges_pair = {}
N_prime = {}
rcv_count = 0

LOCK = threading.Lock()


def main(algo, mode, update_interval, local_port, neighbor_ports, last, cost_change):
    global node_port, init_neighbors, dv, next_hop, send_count, rcv_count
    init_neighbors = neighbor_ports
    for neighbor, edge in neighbor_ports.items():
        dv[neighbor] = edge
        if neighbor != local_port:
            next_hop[neighbor] = neighbor

    node_ip = gethostbyname(gethostname())
    node_port = local_port
    socketServer = socket(AF_INET, SOCK_DGRAM)
    socketServer.bind((node_ip, node_port))

    if algo == "dv":
        if last:
            if cost_change is not None:
                timer = threading.Timer(30, cost_change_fuc, (cost_change, ))
                timer.setDaemon(True)
                timer.start()
            send_count = 1
            sendDv()

        while True:
            message, client_addr = socketServer.recvfrom(BUFFER)
            t = threading.Thread(target=start_fuc, args=(message,))
            t.setDaemon(True)
            t.start()

    elif algo == "ls":
        for neighbor, edge in neighbor_ports.items():
            all_edges_pair[(node_port, neighbor)] = edge
            all_edges_pair[(neighbor, node_port)] = edge

        if last:
            if cost_change is not None:
                timer = threading.Timer(30, cost_change_func_ls, (cost_change, ))
                timer.setDaemon(True)
                timer.start()
            sendLSA()

        while True:
            message, client_addr = socketServer.recvfrom(BUFFER)
            t = threading.Thread(target=start_func_LSA, args=(message, update_interval))
            t.setDaemon(True)
            t.start()

            if rcv_count == 0:
                t1 = threading.Thread(target=periodic_update, args=(update_interval, ))
                t1.setDaemon(True)
                t1.start()
            rcv_count += 1


def start_fuc(message):
    LOCK.acquire()
    modifiedMessage = message.decode().split(';')
    head = modifiedMessage[0]
    modifiedMessage = modifiedMessage[1:]

    if head == HEAD1:
        if len(modifiedMessage) == 0:
            LOCK.release()
            return -1
        # print(modifiedMessage)
        from_port = int(modifiedMessage[0])
        neighbor_dv = {}
        for j in range(1, len(modifiedMessage), 1):
            if len(modifiedMessage[j]) > 1:
                to_port = int(modifiedMessage[j].split()[0])
                distance = int(modifiedMessage[j].split()[1])
                neighbor_dv[to_port] = distance

        timestamp = round(time(), 3)
        print("[", timestamp, "] Message received at Node {toN} from Node {fromN}\n".format(fromN=from_port,
                                                                                            toN=node_port))
        update(from_port, neighbor_dv)

    if head == HEAD2:  # link cost change
        from_port = int(modifiedMessage[0])
        init_neighbors[from_port] = int(modifiedMessage[1])
        timestamp = round(time(), 3)
        print("[", timestamp, "] Link value message received at Node {portv} from Node {portx}\n".format(portv=node_port,
                                                                                                         portx=from_port))
        if init_neighbors[from_port] < dv[from_port]:  # new edge is smaller than the original min path
            dv[from_port] = init_neighbors[from_port]
            sendDv()

    LOCK.release()
    return 0


def start_func_LSA(message, update_interval):
    LOCK.acquire()
    modifiedMessage = message.decode().split(';')
    head = modifiedMessage[0]
    modifiedMessage = modifiedMessage[1:]

    if head == HEAD1:
        if len(modifiedMessage) == 0:
            LOCK.release()
            return -1

        origin_port = int(modifiedMessage[0])
        seq = modifiedMessage[1]

        """
        If this is a new LSA or new seq
        """
        if origin_port not in other_ports_lsa.keys() or other_ports_lsa[origin_port] < seq:
            other_ports_lsa[origin_port] = seq
            for j in range(2, len(modifiedMessage)):
                if len(modifiedMessage[j]) == 0:
                    continue
                to_port = int(modifiedMessage[j].split()[0])
                dist = int(modifiedMessage[j].split()[1])
                all_edges_pair[(origin_port, to_port)] = dist
                all_edges_pair[(to_port, origin_port)] = dist

            timestamp = round(time.time(), 3)
            print("[", timestamp, "] LSA of node {port} with sequence number {xxx} received from Node {from_port}".format(port=node_port,
                                                                                                                          xxx=seq,
                                                                                                                          from_port=origin_port))
            dijkstra()

            """
            forwarding message
            """
            sendSocket = socket(AF_INET, SOCK_DGRAM)
            for neighbor in init_neighbors.keys():
                if neighbor != node_port:
                    sendSocket.sendto(message, (gethostbyname(gethostname()), neighbor))
            sendSocket.close()

    LOCK.release()
    return 0

"""
update dv{}
"""
def dijkstra():
    pass


def periodic_update(update_interval):
    while True:
        try:
            sleep(update_interval + random.random())
            seq = time() * 10000000
            message = "" + HEAD1 + ";" + str(node_port) + ";" + str(seq)

            LOCK.acquire()
            for neighbor in init_neighbors:
                if neighbor != node_port:
                    message = message + ";"
                    message = message + str(neighbor) + " " + str(init_neighbors[neighbor])

            sendSocket = socket(AF_INET, SOCK_DGRAM)
            for neighbor in init_neighbors:
                if neighbor != node_port:
                    sendSocket.sendto(message.encode(), (gethostbyname(gethostname()), neighbor))
                    print("[", round(seq / 10000000, 3),
                          "] LSA of Node {from_port} with sequence number {seq} sent to Node {to_port}".format(from_port=node_port,
                                                                                                               seq=seq,
                                                                                                               to_port=neighbor))

            dijkstra()
            LOCK.release()
        except InterruptedError:
            break
    return 0


def update(from_port, neighbor_dv):
    global dv, send_count, next_hop
    isChanged = False

    for port in neighbor_dv.keys():
        if port not in dv.keys():  # distance is infinity
            dv[port] = init_neighbors[from_port] + neighbor_dv[port]
            next_hop[port] = from_port
            isChanged = True
        else:  # its dv has this port
            if init_neighbors[from_port] + neighbor_dv[port] < dv[port]:  # from from_port to here
                next_hop[port] = from_port
                isChanged = True
            dv[port] = min(init_neighbors[from_port] + neighbor_dv[port], dv[port])

    if isChanged or send_count == 0:
        send_count += 1
        sendDv()

    sorted(dv.keys())
    timestamp = round(time(), 3)
    print("[", timestamp, "] Node {node} Routing Table\n".format(node=node_port))
    for port in sorted(dv.keys()):
        if port != node_port:
            print("- {distance} -> Node {toPort}; Next hop -> Node {nexthop}\n".format(distance=dv[port],
                                                                                       toPort=port,
                                                                                       nexthop=next_hop[port]))


def sendDv():
    message = HEAD1 + ";" + str(node_port) + ";"
    for key in dv.keys():
        message = message + str(key) + " " + str(dv[key]) + ";"

    sendSocket = socket(AF_INET, SOCK_DGRAM)
    for neighbor in init_neighbors.keys():
        if neighbor != node_port:
            timestamp = round(time(), 3)
            print("[", timestamp, "] Message sent from Node {fromN} to Node {toN}\n".format(fromN=node_port,
                                                                                            toN=neighbor))
            sendSocket.sendto(message.encode(), (gethostbyname(gethostname()), int(neighbor)))

    sendSocket.close()


def sendLSA():
    pass


def cost_change_fuc(cost_change):
    LOCK.acquire()
    heighest_neighbor_port = sorted(init_neighbors.keys())[-1]
    if heighest_neighbor_port == node_port:
        heighest_neighbor_port = sorted(init_neighbors.keys())[-2]
    init_neighbors[heighest_neighbor_port] = int(cost_change)
    timestamp = round(time(), 3)
    print("[", timestamp, "] Node {port}-{xxxx} cost updated to {value}\n".format(port=node_port,
                                                                                  xxxx=heighest_neighbor_port,
                                                                                  value=cost_change))
    if dv[heighest_neighbor_port] > int(cost_change):
        dv[heighest_neighbor_port] = int(cost_change)

    message = HEAD2 + ";" + str(node_port) + ";" + str(cost_change)
    sendSocket = socket(AF_INET, SOCK_DGRAM)
    if heighest_neighbor_port != node_port:
        sendSocket.sendto(message.encode(), (gethostbyname(gethostname()), int(heighest_neighbor_port)))
        timestamp = round(time(), 3)
        print("[", timestamp, "] Link value message sent from Node {portx} to Node {portv}\n".format(portx=node_port,
                                                                                                     portv=heighest_neighbor_port))

    sendSocket.close()
    sendDv()
    LOCK.release()

def cost_change_func_ls(cost_change):
    pass


if __name__ == "__main__":
    # p = sys.argv
    #p = ["", "dv", "r", "1111", "2222", "1", "3333", "50"]
    #p = ["", "dv", "r", "2222", "1111", "1", "3333", "2", "4444", "8"]
    #p = ["", "dv", "r", "3333", "1111", "50", "2222", "2", "4444", "5"]
    p = ["", "dv", "r", "4444", "2222", "8", "3333", "5", "last", "1"]
    if len(p) < 5:
        print("Too less parameters! \n")
        exit(1)

    algo = p[1]
    start = None
    if algo == "dv":
        start = 4
    elif algo == "ls":
        start = 5
    else:
        print("Wrong routing algo!\n")
        exit(1)

    mode = p[2]
    if mode != "r" and mode != "p":
        print("Mode must be 'r' or 'p'! got '{mode}'\n".format(mode=mode))
        exit(1)

    local_port = None
    update_interval = None
    if start == 4:
        local_port = p[3]
    elif start == 5:
        update_interval = p[3]
        local_port = p[4]

    last = False
    cost_change = None
    neighbor_ports = {int(local_port): 0}
    for i in range(start, len(p), 2):
        if p[i] == "last":  # indication of last node
            last = True
            if i + 1 >= len(p):
                break
            else:
                cost_change = p[i + 1]
        else:
            neighbor_ports[int(p[i])] = int(p[i + 1])

    main(algo=algo, mode=mode, update_interval=update_interval, local_port=int(local_port),
         neighbor_ports=neighbor_ports, last=last, cost_change=cost_change)
