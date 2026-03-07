import eventlet
eventlet.monkey_patch()

worker_class = "eventlet"
workers = 1
timeout = 120
