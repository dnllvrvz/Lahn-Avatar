#!/bin/bash

BACKEND=lahn-backend
FRONTEND=lahn-frontend

usage() {
  echo "Usage: avatars.sh [command]"
  echo ""
  echo "Commands:"
  echo "  start      Start backend and frontend"
  echo "  stop       Stop backend and frontend"
  echo "  restart    Restart backend and frontend"
  echo "  status     Show status of both services"
  echo "  logs       Tail backend log (Ctrl+C to exit)"
  echo "  -b start|stop|restart|status    Backend only"
  echo "  -f start|stop|restart|status    Frontend only"
}

case "$1" in
  start)
    systemctl start $BACKEND $FRONTEND
    systemctl status $BACKEND $FRONTEND --no-pager | grep -E "Active|●"
    ;;
  stop)
    systemctl stop $BACKEND $FRONTEND
    echo "Both services stopped."
    ;;
  restart)
    systemctl restart $BACKEND $FRONTEND
    systemctl status $BACKEND $FRONTEND --no-pager | grep -E "Active|●"
    ;;
  status)
    systemctl status $BACKEND $FRONTEND --no-pager | grep -E "Active|●|Main PID"
    ;;
  logs)
    tail -f /root/backend_log.0
    ;;
  -b)
    systemctl $2 $BACKEND
    [ "$2" = "status" ] && systemctl status $BACKEND --no-pager | grep -E "Active|●|Main PID"
    ;;
  -f)
    systemctl $2 $FRONTEND
    [ "$2" = "status" ] && systemctl status $FRONTEND --no-pager | grep -E "Active|●|Main PID"
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage
    ;;
esac
