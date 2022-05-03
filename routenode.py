import random
import socket
import sys
import threading
import time
from socket import *
from time import *

import numpy as np

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
N_prime = []
periodic_update_start = 0
topology_changed = False

LOCK = threading.Lock()


def main(algo, mode, update_interval, local_port, neighbor_ports, last, cost_change):
    global node_port, init_neighbors, dv, next_hop, send_count, periodic_update_start
    init_neighbors = neighbor_ports
    next_hop[local_port] = local_port
    for neighbor, edge in neighbor_ports.items():
        dv[neighbor] = edge
        # if neighbor != local_port:
        next_hop[neighbor] = neighbor

    node_ip = gethostbyname(gethostname())
    node_port = local_port
    socketServer = socket(AF_INET, SOCK_DGRAM)
    socketServer.bind((node_ip, node_port))

    if algo == "dv":
        if last:
            if cost_change is not None:
                timer = threading.Timer(30, cost_change_fuc, (cost_change, "dv"))
                timer.setDaemon(True)
                timer.start()
            send_count = 1
            sendDv()  # doesn't acquire a lock, concurrent risk

        while True:
            try:
                message, client_addr = socketServer.recvfrom(BUFFER)
                t = threading.Thread(target=start_fuc, args=(message, mode))
                t.setDaemon(True)
                t.start()
            except InterruptedError:
                return 0

    elif algo == "ls":
        for neighbor, edge in neighbor_ports.items():
            all_edges_pair[(node_port, neighbor)] = edge
            all_edges_pair[(neighbor, node_port)] = edge

        if last:
            if cost_change is not None:
                timer = threading.Timer(30*1.2, cost_change_fuc, (cost_change, "ls"))
                timer.setDaemon(True)
                timer.start()
            sendLSA()

        while True:
            try:
                message, client_addr = socketServer.recvfrom(BUFFER)
                t = threading.Thread(target=start_func_LSA, args=(message, int(update_interval)))
                t.setDaemon(True)
                t.start()

                if periodic_update_start == 0:
                    t1 = threading.Thread(target=periodic_update, args=(int(update_interval), ))
                    t1.setDaemon(True)
                    t1.start()
                    t2 = threading.Thread(target=update_every_routing_interval, args=(int(ROUTING_INTERVAL),))
                    t2.setDaemon(True)
                    t2.start()
                    periodic_update_start += 1
            except InterruptedError:
                return 0


def start_fuc(message, mode):
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

    if head == HEAD2:  # link cost change, this should force the node replace dv with next hop equal to from_port
        from_port = int(modifiedMessage[0])
        new_edge = int(modifiedMessage[1])
        original_edge = init_neighbors[from_port]
        init_neighbors[from_port] = new_edge

        timestamp = round(time(), 3)
        print("[", timestamp, "] Link value message received at Node {portv} from Node {portx}\n".format(portv=node_port,
                                                                                                 portx=from_port))
        # # wait until the sendDV message from from_port to change this
        # if init_neighbors[from_port] < dv[from_port]:  # new edge is smaller than the original min path
        #     dv[from_port] = init_neighbors[from_port]
        #     sendDv()

        for to_port in dv.keys():
            if next_hop[to_port] == from_port:
                dv[to_port] = dv[to_port] - original_edge + new_edge

        sendDv()

    LOCK.release()
    return 0


def start_func_LSA(message, update_interval):
    global topology_changed
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
                """
                if topology table is changed
                """
                if (origin_port, to_port) not in all_edges_pair.keys() or all_edges_pair[(origin_port, to_port)] != dist:
                    topology_changed = True
                all_edges_pair[(origin_port, to_port)] = dist
                all_edges_pair[(to_port, origin_port)] = dist

            timestamp = round(time(), 3)
            print("[", timestamp, "] LSA of node {port} with sequence number {xxx} received from Node {from_port}".format(port=node_port,
                                                                                                                          xxx=seq,
                                                                                                                          from_port=origin_port))
            if topology_changed:
                timestamp = round(time(), 3)
                print("[", timestamp, "] topology update:")
                for tup in sorted(all_edges_pair.keys()):
                    if tup[0] < tup[1]:
                        print("edge {fromN} -> {toN} distance is {dist}".format(fromN=tup[0], toN=tup[1], dist=all_edges_pair[tup]))
                dijkstra()
                topology_changed = False

            """
            forwarding message
            """
            sendSocket = socket(AF_INET, SOCK_DGRAM)
            for neighbor in init_neighbors.keys():
                if neighbor != node_port:
                    sendSocket.sendto(message, (gethostbyname(gethostname()), neighbor))
            sendSocket.close()

    if head == HEAD2:
        from_port = int(modifiedMessage[0])
        init_neighbors[from_port] = int(modifiedMessage[1])
        timestamp = round(time(), 3)
        print("[", timestamp, "] Link value message received at Node {portv} from Node {portx}\n".format(portv=node_port,
                                                                                                         portx=from_port))

    LOCK.release()
    return 0


def update_every_routing_interval(routing_interval):
    while True:
        sleep(routing_interval)
        LOCK.acquire()
        dijkstra()
        LOCK.release()


def dijkstra():
    """
    update dv{},  do not need to acquire lock
    """
    global N_prime, dv, next_hop
    N_prime = [node_port]
    dv = {node_port: 0}
    for tup_port in all_edges_pair.keys():
        if tup_port[0] == node_port:
            dv[tup_port[1]] = all_edges_pair[tup_port]

    for tup_port in all_edges_pair.keys():
        if tup_port[0] != node_port and tup_port[1] != node_port and tup_port[0] not in dv.keys():  # not directly connected node
            dv[tup_port[0]] = np.inf

    while len(N_prime) < len(dv.keys()):
        min_dw = np.inf
        min_port = None
        for to_port, dw in dv.items():
            if to_port not in N_prime and dw < min_dw:
                min_dw = dw
                min_port = to_port

        N_prime.append(min_port)
        for tup, dis in all_edges_pair.items():
            w = tup[0]
            v = tup[1]
            if w == min_port and v not in N_prime:
                if dv[min_port] + dis < dv[v]:
                    next_hop[v] = next_hop[w]  # w = min_port
                dv[v] = min(dv[v], dv[min_port]+dis)

    timestamp = round(time(), 3)
    print("[", timestamp, "] Node {port} Routing Table".format(port=node_port))
    for to_port in sorted(dv.keys()):
        if to_port != node_port:
            if next_hop[to_port] == to_port:
                print("- ({distance}) -> Node {to_port}".format(distance=dv[to_port], to_port=to_port))
            else:
                print("- ({distance}) -> Node {to_port} ; Next hop -> Node {next_port}".format(distance=dv[to_port],
                                                                                               to_port=to_port,
                                                                                               next_port=next_hop[to_port]))

    return 0


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

            # dijkstra()
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
                dv[port] = init_neighbors[from_port] + neighbor_dv[port]
            if next_hop[port] == from_port and dv[port] != init_neighbors[from_port] + neighbor_dv[port]:
                dv[port] = init_neighbors[from_port] + neighbor_dv[port]
                isChanged = True

    if isChanged or send_count == 0:  # if never send or being changed
        send_count += 1
        sendDv()

    sorted(dv.keys())
    timestamp = round(time(), 3)
    print("[", timestamp, "] Node {node} Routing Table\n".format(node=node_port))
    for to_port in sorted(dv.keys()):
        if to_port != node_port:
            if to_port == next_hop[to_port]:
                print("- ({distance}) -> Node {to_port}".format(distance=dv[to_port], to_port=to_port))
            else:
                print("- ({distance}) -> Node {to_Port}; Next hop -> Node {nexthop}".format(distance=dv[to_port],
                                                                                            to_Port=to_port,
                                                                                            nexthop=next_hop[to_port]))


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

    sendSocket.close()
    LOCK.release()

    return 0


def cost_change_fuc(cost_change, algo):
    LOCK.acquire()
    cost_change = int(cost_change)
    highest_neighbor_port = sorted(init_neighbors.keys())[-1]
    if highest_neighbor_port == node_port:
        highest_neighbor_port = sorted(init_neighbors.keys())[-2]

    origin_edge = init_neighbors[highest_neighbor_port]
    init_neighbors[highest_neighbor_port] = int(cost_change)
    timestamp = round(time(), 3)
    print("[", timestamp, "] Node {port}-{xxxx} cost updated to {value}\n".format(port=node_port,
                                                                                  xxxx=highest_neighbor_port,
                                                                                  value=cost_change))
    # if dv[highest_neighbor_port] > int(cost_change):
    #     dv[highest_neighbor_port] = int(cost_change)
    """
    all the nodes reached through highest_neighbor_port's shortest distance will change
    """
    for to_port in dv.keys():
        if next_hop[to_port] == highest_neighbor_port:
            # change the dv with next hop equals to the highest_neighbour_port
            dv[to_port] = dv[to_port] + cost_change - origin_edge

    message = HEAD2 + ";" + str(node_port) + ";" + str(cost_change)
    sendSocket = socket(AF_INET, SOCK_DGRAM)
    sendSocket.sendto(message.encode(), (gethostbyname(gethostname()), int(highest_neighbor_port)))
    timestamp = round(time(), 3)
    print("[", timestamp, "] Link value message sent from Node {portx} to Node {portv}\n".format(portx=node_port,
                                                                                                 portv=highest_neighbor_port))

    sendSocket.close()
    if algo == "dv":
        sendDv()

    LOCK.release()
    return 0

def cost_change_func_ls(cost_change):
    pass


if __name__ == "__main__":
    p = sys.argv
    """
    dv test
    """
    #p = ["", "dv", "r", "2", "1111", "2222", "1", "3333", "50"]
    #p = ["", "dv", "r", "2", "2222", "1111", "1", "3333", "2", "4444", "8"]
    #p = ["", "dv", "r", "2", "3333", "1111", "50", "2222", "2", "4444", "5"]
    #p = ["", "dv", "r", "2", "4444", "2222", "8", "3333", "5", "last", "1"]
    """
    dv test 2
    """
    #p = ["", "dv", "r", "2", "1111", "2222", "1", "3333", "50"]
    #p = ["", "dv", "r", "2", "2222", "1111", "1", "3333", "2"]
    #p = ["", "dv", "r", "2", "3333", "1111", "50", "2222", "2", "last", "60"]
    """
    ls test
    """
    #p = ["", "ls", "r", "2", "1111", "2222", "1", "3333", "50"]
    #p = ["", "ls", "r", "2", "2222", "1111", "1", "3333", "2"]
    #p = ["", "ls", "r", "2", "3333", "1111", "50", "2222", "2", "4444", "5"]
    #p = ["", "ls", "r", "2", "4444", "2222", "8", "3333", "5", "last", "1"]
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

    # local_port = None
    # update_interval = None
    # if start == 4:
    #     local_port = p[4]
    # elif start == 5:
    update_interval = p[3]
    local_port = p[4]

    last = False
    cost_change = None
    neighbor_ports = {int(local_port): 0}
    for i in range(5, len(p), 2):
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
