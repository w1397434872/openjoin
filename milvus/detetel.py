from pymilvus import connections, utility
connections.connect(alias="default", host="localhost", port="19530")
utility.drop_collection("join_agent")