"""Command line for agents: stackpad-cli and StackPad.exe forward their arguments here and print the result.

Commands call the same engine methods as the screen, so every rule the screen follows applies here too.
"""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from groups import PAD_COLORS, PadInput
from padsets import PadsetInput
from i18n import CLI_HELP, EN, translate

HELP = '''StackPad 명령줄

사용법: stackpad-cli <명령> [옵션]

  help [padset|pad]          도움말
  version                    엔진 버전

  padset list                패드셋 목록, 패드 수와 빈 슬롯
  padset add <이름>          패드셋 추가
  padset rename <패드셋> <새 이름>
  padset order <패드셋>...   지정한 순서로 앞에 배치하고 나머지는 기존 순서 유지
  padset delete <패드셋>     빈 패드셋 삭제

  pad list [--padset P]      패드 목록과 상태
  pad show <패드>            패드 상세, input 항목은 --json에 그대로 쓸 수 있습니다
  pad add [옵션]             패드 추가
  pad update <패드> [옵션]   패드 설정 변경, 지정한 옵션만 바뀝니다
  pad move <패드> --slot S [--padset P]
  pad delete <패드>          중지된 패드 삭제
  pad start <패드> [--takeover]
  pad stop <패드>
  pad restart <패드>
  pad logs <패드> [--component C]

패드와 패드셋은 ID 또는 이름(대소문자 무시)으로 지정합니다.
결과는 JSON으로 출력하며 pad logs와 help만 텍스트입니다.
종료 코드: 0 성공, 1 실행 오류, 2 명령 형식 오류, 3 엔진 연결 실패'''

PAD_HELP = '''pad add, pad update 옵션

  --name N                  패드 이름 (add에서 필수)
  --padset P                패드셋, 기본값은 첫 패드셋
  --slot S                  0~15, 왼쪽 위부터 행 순서. 기본값은 첫 빈 슬롯
  --color C                 패드 색상
  --autostart / --no-autostart       Windows 시작 시 실행
  --wait-ready / --no-wait-ready     그룹 시작 때 구성마다 준비 확인
  --domain-url U, --local-url U      패드 메뉴의 열기 주소, 빈 값이면 지웁니다

단일 구성 옵션
  --command CMD --cwd DIR   로컬 명령과 작업 폴더. --cwd 기본값은 현재 폴더
  --port N                  확인할 포트, none이면 지웁니다
  --health-url U            로컬 상태 확인 주소
  --container NAME          Docker 컨테이너

--json FILE|-  패드 전체 설정 JSON 파일 또는 표준 입력. 그룹 패드와 원격 서버 패드는 이 방식으로 지정합니다.
  {"name": "앱", "components": [{"kind": "local", "name": "API", "command": "uv run main.py", "cwd": "D:/app", "port": 8000},
                                {"kind": "remote", "name": "DB", "remote": {"host": "nas", "start": "...", "stop": "...", "status": "..."}}]}
  update에서 구성의 id를 빼면 새 구성으로 바뀝니다. pad show의 input을 고쳐서 넘기면 안전합니다.

색상:'''

PADSET_HELP = '''padset 명령

  padset list
  padset add <이름>
  padset rename <패드셋> <새 이름>
  padset order <패드셋>...
  padset delete <패드셋>     패드를 옮기거나 지운 다음 삭제할 수 있습니다'''


EN.update({HELP: CLI_HELP['main'], PAD_HELP: CLI_HELP['pad'], PADSET_HELP: CLI_HELP['padset']})


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parser():
    root = Parser(prog='stackpad-cli', add_help=False)
    commands = root.add_subparsers(dest='area')
    commands.add_parser('help', add_help=False).add_argument('topic', nargs='?')
    commands.add_parser('version', add_help=False)

    padset = commands.add_parser('padset', add_help=False).add_subparsers(dest='action', required=True)
    padset.add_parser('list', add_help=False)
    padset.add_parser('add', add_help=False).add_argument('name')
    rename = padset.add_parser('rename', add_help=False)
    rename.add_argument('padset')
    rename.add_argument('name')
    padset.add_parser('order', add_help=False).add_argument('padsets', nargs='+')
    padset.add_parser('delete', add_help=False).add_argument('padset')

    pad = commands.add_parser('pad', add_help=False).add_subparsers(dest='action', required=True)
    pad.add_parser('list', add_help=False).add_argument('--padset')
    pad.add_parser('show', add_help=False).add_argument('pad')
    for action in ('add', 'update'):
        command = pad.add_parser(action, add_help=False)
        if action == 'update':
            command.add_argument('pad')
        command.add_argument('--json', dest='json_source')
        command.add_argument('--name')
        command.add_argument('--padset')
        command.add_argument('--slot', type=int)
        command.add_argument('--color')
        command.add_argument('--autostart', action=argparse.BooleanOptionalAction)
        command.add_argument('--wait-ready', action=argparse.BooleanOptionalAction)
        command.add_argument('--domain-url')
        command.add_argument('--local-url')
        command.add_argument('--command')
        command.add_argument('--cwd')
        command.add_argument('--port')
        command.add_argument('--health-url')
        command.add_argument('--container')
    move = pad.add_parser('move', add_help=False)
    move.add_argument('pad')
    move.add_argument('--slot', type=int, required=True)
    move.add_argument('--padset')
    for action in ('delete', 'stop', 'restart'):
        pad.add_parser(action, add_help=False).add_argument('pad')
    start = pad.add_parser('start', add_help=False)
    start.add_argument('pad')
    start.add_argument('--takeover', action='store_true')
    logs = pad.add_parser('logs', add_help=False)
    logs.add_argument('pad')
    logs.add_argument('--component')
    return root


def find_padset(engine, ref):
    sets = engine.config['padsets']
    found = [s for s in sets if s['id'] == ref] or [s for s in sets if s['name'].casefold() == ref.strip().casefold()]
    if not found:
        raise KeyError(f'패드셋을 찾을 수 없습니다: {ref}')
    return found[0]


def group_status(members):
    """Same rules as the pad screen, so a group reads the same here and there."""
    active = [s for s in members if s.get('active')]
    statuses = [s.get('status') for s in members]
    if not active and 'conflict' in statuses:
        return 'conflict'
    if not active and 'external' in statuses:
        return 'external'
    if any(s in ('unhealthy', 'error', 'unreachable') for s in statuses):
        return 'unhealthy' if active else 'error' if 'error' in statuses else 'unreachable'
    if not active:
        return 'checking' if 'checking' in statuses else 'stopped'
    if len(active) < len(members):
        return 'partial'
    return 'starting' if 'starting' in statuses else 'running'


def component_settings(service):
    kind = service.get('kind') or 'local'
    if kind == 'remote':
        return {'remote': service.get('remote')}
    if kind == 'docker':
        return {'container': service.get('container', '')}
    return {key: service.get(key) for key in ('command', 'cwd', 'port', 'health_url')}


def all_pads(engine):
    services = {s['id']: s for s in engine.snapshot()}
    names = {s['id']: s['name'] for s in engine.config['padsets']}
    order = {s['id']: index for index, s in enumerate(engine.config['padsets'])}
    groups = engine.config.get('groups', [])
    grouped = {sid for g in groups for sid in g['member_ids']}
    pads = [(g, [services[sid] for sid in g['member_ids'] if sid in services], True) for g in groups]
    pads += [(s, [s], False) for s in services.values() if s['id'] not in grouped]
    result = []
    for pad, members, is_group in pads:
        result.append({
            'id': pad['id'], 'name': pad['name'], 'padset_id': pad['padset_id'], 'padset': names.get(pad['padset_id'], ''), 'slot': pad['slot'],
            'type': 'group' if is_group else 'single', 'status': group_status(members) if is_group else members[0].get('status'),
            'color': pad.get('color'), 'autostart': bool(pad.get('autostart')),
            'components': [{'id': s['id'], 'name': s['name'], 'kind': s.get('kind') or 'local', 'status': s.get('status'), 'pid': s.get('pid'),
                            'error': s.get('error') or s.get('message') or '', **component_settings(s)} for s in members],
            '_order': (order.get(pad['padset_id'], 0), pad['slot']), '_group': is_group, '_pad': pad,
        })
    return sorted(result, key=lambda p: p['_order'])


def public(pad, detail=False):
    view = {k: v for k, v in pad.items() if not k.startswith('_')}
    if not detail:
        view['components'] = [{k: c[k] for k in ('id', 'name', 'kind', 'status')} for c in pad['components']]
    return view


def find_pad(engine, ref):
    pads = all_pads(engine)
    found = [p for p in pads if p['id'] == ref] or [p for p in pads if p['name'].casefold() == ref.strip().casefold()]
    if not found:
        raise KeyError(f'패드를 찾을 수 없습니다: {ref}')
    if len(found) > 1:
        candidates = ', '.join(f"{p['id']} ({p['padset']})" for p in found)
        raise ValueError(f'같은 이름의 패드가 여러 개입니다. ID로 지정해 주세요: {candidates}')
    return found[0]


def pad_input(engine, pad):
    """The body PadInput accepts for this pad, so update can change only what was asked."""
    source = pad['_pad']
    members = [engine.service(c['id']) for c in pad['components']]
    components = [{'id': s['id'], 'kind': s.get('kind') or 'local', 'name': s['name'], **component_settings(s)} for s in members]
    for component in components:
        if component['kind'] == 'local':
            component['port'] = component['port'] or None
            component['health_url'] = component['health_url'] or ''
    return {'name': source['name'], 'slot': source['slot'], 'padset_id': source['padset_id'], 'color': source.get('color', '#22c55e'),
            'autostart': bool(source.get('autostart')), 'wait_ready': bool(source.get('wait_ready')), 'components': components,
            'domain_url': source.get('domain_url', ''), 'local_url': source.get('local_url', '')}


def read_json(source, context):
    if source == '-':
        text = context['stdin']
    else:
        path = Path(source)
        text = (path if path.is_absolute() else Path(context['cwd']) / path).read_text('utf-8-sig')
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'JSON 형식을 확인해 주세요: {error}') from error
    if not isinstance(data, dict):
        raise ValueError('패드 설정 JSON은 객체로 입력해 주세요.')
    return data


def folder(value, context):
    path = Path(value)
    return str(path if path.is_absolute() else Path(context['cwd']) / path)


def color(value):
    value = value.strip().lower()
    if value not in PAD_COLORS:
        raise ValueError('제공된 패드 색상을 선택해 주세요.')
    return value


def first_free_slot(engine, padset_id, ignore=()):
    used = {s['slot'] for s in engine.config['services'] if s['padset_id'] == padset_id and s['id'] not in ignore}
    free = [slot for slot in range(16) if slot not in used]
    if not free:
        raise ValueError('패드셋에 빈 슬롯이 없습니다.')
    return free[0]


def pad_body(engine, args, context, base=None):
    body = dict(base or {})
    if args.json_source:
        body.update(read_json(args.json_source, context))
    if args.name is not None:
        body['name'] = args.name
    if args.padset is not None:
        body['padset_id'] = args.padset
    if body.get('padset_id'):
        body['padset_id'] = find_padset(engine, body['padset_id'])['id']
    else:
        body['padset_id'] = engine.config['padsets'][0]['id']
    if args.slot is not None:
        body['slot'] = args.slot
    if args.color is not None:
        body['color'] = color(args.color)
    for key in ('autostart', 'wait_ready', 'domain_url', 'local_url'):
        if getattr(args, key) is not None:
            body[key] = getattr(args, key)
    local = {key: getattr(args, key) for key in ('command', 'cwd', 'port', 'health_url') if getattr(args, key) is not None}
    if local or args.container is not None:
        components = body.get('components') or []
        if len(components) > 1:
            raise ValueError('여러 구성을 가진 패드는 --json으로 구성을 지정해 주세요.')
        component = dict(components[0]) if components else {}
        component['name'] = body.get('name') or component.get('name') or ''
        if args.container is not None:
            component = {'id': component.get('id'), 'name': component['name'], 'kind': 'docker', 'container': args.container}
        else:
            if component.get('kind', 'local') != 'local':
                component = {'id': component.get('id'), 'name': component['name']}
            component['kind'] = 'local'
            if 'cwd' in local:
                local['cwd'] = folder(local['cwd'], context)
            elif not component.get('cwd'):
                local['cwd'] = context['cwd']
            if 'port' in local:
                local['port'] = None if local['port'].strip().lower() in ('', 'none') else local['port']
            component.update(local)
        body['components'] = [{k: v for k, v in component.items() if v is not None or k == 'port'}]
    if len(body.get('components') or []) == 1 and body.get('name'):
        # A single pad shows its component, so both carry the pad name.
        body['components'][0]['name'] = body['name']
    return body


def mutate(engine, values, pad_id=None):
    data = PadInput.model_validate(values)
    return engine.save_pad(data, pad_id)


def pad_result(engine, pad_id):
    pad = next((p for p in all_pads(engine) if p['id'] == pad_id), None)
    return {'ok': True, 'pad': public(pad, detail=True) if pad else None}


def padset_list(engine):
    counts, used = {}, {}
    for service in engine.config['services']:
        used.setdefault(service['padset_id'], set()).add(service['slot'])
    for pad in all_pads(engine):
        counts[pad['padset_id']] = counts.get(pad['padset_id'], 0) + 1
    return {'padsets': [{'id': s['id'], 'name': s['name'], 'pads': counts.get(s['id'], 0),
                         'free_slots': [slot for slot in range(16) if slot not in used.get(s['id'], set())]} for s in engine.config['padsets']]}


def run_padset(engine, args, context):
    if args.action == 'list':
        return padset_list(engine)
    if args.action == 'add':
        padset_id = engine.save_padset(PadsetInput(name=args.name))
        return {'ok': True, 'id': padset_id, 'name': args.name.strip()}
    if args.action == 'rename':
        padset_id = find_padset(engine, args.padset)['id']
        engine.save_padset(PadsetInput(name=args.name), padset_id)
        return {'ok': True, 'id': padset_id, 'name': args.name.strip()}
    if args.action == 'order':
        chosen = []
        for ref in args.padsets:
            padset_id = find_padset(engine, ref)['id']
            if padset_id not in chosen:
                chosen.append(padset_id)
        rest = [s['id'] for s in engine.config['padsets'] if s['id'] not in chosen]
        engine.reorder_padsets(chosen + rest)
        return {'ok': True, **padset_list(engine)}
    padset = find_padset(engine, args.padset)
    engine.delete_padset(padset['id'])
    return {'ok': True, 'id': padset['id'], 'name': padset['name']}


def run_pad(engine, args, context):
    if args.action == 'list':
        padset_id = find_padset(engine, args.padset)['id'] if args.padset else None
        return {'pads': [public(p) for p in all_pads(engine) if not padset_id or p['padset_id'] == padset_id]}
    if args.action == 'add':
        body = pad_body(engine, args, context)
        if not body.get('name'):
            raise ValueError('--name으로 패드 이름을 입력해 주세요.')
        if not body.get('components'):
            raise ValueError('--command, --container 또는 --json으로 구성을 입력해 주세요.')
        body.setdefault('slot', first_free_slot(engine, body['padset_id']))
        return pad_result(engine, mutate(engine, body))
    pad = find_pad(engine, args.pad)
    if args.action == 'show':
        return {**public(pad, detail=True), 'input': pad_input(engine, pad)}
    if args.action == 'update':
        base = pad_input(engine, pad)
        body = pad_body(engine, args, context, base)
        if body['padset_id'] != base['padset_id'] and body['slot'] == base['slot'] and args.slot is None:
            # Moving to another padset without a slot takes that set's first free slot.
            body['slot'] = first_free_slot(engine, body['padset_id'])
        return pad_result(engine, mutate(engine, body, pad['id']))
    if args.action == 'move':
        engine.move_pad(pad['id'], args.slot, find_padset(engine, args.padset)['id'] if args.padset else None)
        return pad_result(engine, pad['id'])
    if args.action == 'delete':
        engine.delete_pad(pad['id'])
        return {'ok': True, 'id': pad['id'], 'name': pad['name']}
    if args.action == 'logs':
        components = pad['components']
        if args.component:
            components = [c for c in components if args.component in (c['id'],) or c['name'].casefold() == args.component.strip().casefold()]
            if not components:
                raise KeyError(f'구성을 찾을 수 없습니다: {args.component}')
        if len(components) == 1:
            return engine.tail(components[0]['id'])
        return ''.join(f"===== {c['name']} =====\n{engine.tail(c['id'])}\n" for c in components)
    if pad['_group']:
        if args.action == 'restart':
            engine.group_action(pad['id'], 'stop')
            engine.group_action(pad['id'], 'start')
        else:
            engine.group_action(pad['id'], args.action, takeover=getattr(args, 'takeover', False))
    elif args.action == 'start':
        engine.start(pad['id'], args.takeover)
    elif args.action == 'stop':
        engine.stop(pad['id'])
    else:
        engine.restart(pad['id'])
    return pad_result(engine, pad['id'])


def message(error, lang):
    if isinstance(error, ValidationError):
        lines = []
        for item in error.errors():
            where = '.'.join(str(part) for part in item.get('loc', ()))
            text = translate(item.get('msg', ''), lang).removeprefix('Value error, ')
            lines.append(f'{where}: {text}' if where else text)
        return '\n'.join(lines)
    text = str(error)
    if isinstance(error, KeyError):
        text = text.strip("'\"")
    return translate(text, lang)


def run(engine, argv, cwd='', stdin='', lang='ko', version=''):
    """Returns (exit code, standard output, error text)."""
    context = {'cwd': cwd or str(Path.home()), 'stdin': stdin}
    try:
        args = parser().parse_args(argv)
    except UsageError as error:
        return 2, '', translate(f'명령 형식을 확인해 주세요: {error}', lang) + '\n' + translate('stackpad-cli help로 사용법을 볼 수 있습니다.', lang)
    if args.area in (None, 'help'):
        topic = getattr(args, 'topic', None)
        text = translate({'pad': PAD_HELP, 'padset': PADSET_HELP}.get(topic, HELP), lang)
        if topic == 'pad':
            text += ' ' + ' '.join(PAD_COLORS)
        return 0, text + '\n', ''
    try:
        if args.area == 'version':
            result = {'engine': version}
        else:
            result = (run_padset if args.area == 'padset' else run_pad)(engine, args, context)
    except (ValueError, KeyError, RuntimeError, OSError) as error:
        return 1, '', message(error, lang)
    if isinstance(result, str):
        return 0, result if result.endswith('\n') or not result else result + '\n', ''
    return 0, json.dumps(result, ensure_ascii=False, indent=2) + '\n', ''
