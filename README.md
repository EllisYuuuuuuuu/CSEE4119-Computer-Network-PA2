# CSEE4119-Computer-Network-PA2
## Section 2 Distance-Vector Routing Algorithm 
Solution working. I use the main thread to receive message from other router, once receiving a message, update the dv table (if anything changed) and send its own dv to neighbour nodes. I also set a thread run after 30 seconds and set the edge from last node to the neighbour node with highest port. In each node, every thread need to get a lock first to view or modify neighbour edges or dv tables to ensure conccurent safty.

For test case on pdf assignment:

$ python3 ./routenode.py dv r [any-num] 1111 2222 1 3333 50
$ python3 ./routenode.py dv r [any-num] 2222 1111 1 3333 2 4444 8
$ python3 ./routenode.py dv r [any-num] 3333 1111 50 2222 2 4444 5
$ python3 ./routenode.py dv r [any-num] 4444 2222 8 3333 5 last 1

It can produce the expected result on 5.4.0-1072-gcp (need python3 and numpy installed)



## Section 3 Link State Routing Protocol
Solution working. I Use the timestamp*10000000 which is an integer as the LSA sequence number, which statisfy the unique and increasing requirements. The main thread is used for listening from UDP message from other nodes. Once receiving a message from other nodes, it start a periodic thread which will send LSA to neighbour node in ```update_interval```. Once the topology table changed,  it will call dijkstra algorithm to update for a new route table. I also set up a thread actived after the first message received and working per ```ROUTE_INTERVAL``` to call the dijkstra algorithm.


For test case on pdf assignment:

$ python3 ./routenode.py ls r 2 1111 2222 1 3333 50
$ python3 ./routenode.py ls r 2 2222 1111 1 3333 2 4444 8
$ python3 ./routenode.py ls r 2 3333 1111 50 2222 2 4444 5
$ python3 ./routenode.py ls r 2 4444 2222 8 3333 5 last 1

It can produce the expected result on 5.4.0-1072-gcp (need python3 and numpy installed)