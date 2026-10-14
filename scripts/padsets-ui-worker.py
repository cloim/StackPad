"""Isolated API fixture: container effects are simulated, padset persistence is real."""
import json
import sys
import tempfile
import contextlib
from pathlib import Path
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import docker_services
import engine
import main
import ui_session

running = False
container_id = 'a' * 64


def docker(*args):
    global running
    if args[0] == 'ls':
        return json.dumps({'ID': container_id, 'Names': 'test-api', 'Image': 'nginx:alpine', 'Status': 'Up' if running else 'Exited'})
    if args[0] == 'inspect':
        if args[2] == '{{.Id}}':
            return container_id
        return json.dumps({'state': {'Running': running, 'ExitCode': 0, 'StartedAt': '2026-10-12T00:00:00Z'}, 'name': '/test-api', 'ports': {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8080'}]}})
    if args[0] == 'start':
        running = True
    elif args[0] == 'stop':
        running = False
    elif args[0] == 'logs':
        return 'Container ready\n'
    return ''


if __name__ == '__main__':
    docker_services.docker_cli = docker
    engine.docker_cli = docker
    main.collect_usage = lambda **kwargs: []
    with contextlib.ExitStack() as stack:
        directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='stackpad-padsets-ui-'))
        ui_session.seed(directory)
        main.select_folder = lambda current: stack.enter_context(tempfile.TemporaryDirectory(prefix='stackpad-selected-'))
        uvicorn.run(main.create_app(directory, Path(__file__).resolve().parents[1] / 'dist'), host='127.0.0.1', port=48743)
