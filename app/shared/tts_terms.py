# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Terms dictionary for question-voice synthesis.

The Russian Silero voices synthesize from a Cyrillic token set: Latin letters
and digits are silently dropped from the audio. Interview questions mix
Russian prose with Latin technical terms (Kubernetes, CI/CD, PostgreSQL…),
so before synthesis the text is rewritten the way engineers say it aloud.
The on-screen text is unchanged — only the audio.

Order: phrase fixes (CI/CD, I/O) → dictionary → letter-by-letter
abbreviations → simple transliteration of the remaining English words →
numbers spelled out in words. Other locales keep the original text —
Latin-script voices pronounce Latin terms and digits natively.
"""

import re
from typing import Final

# Terms: lowercase key → how engineers pronounce it.
RU_TERMS: Final[dict[str, str]] = {
    # Частые слова из вопросов
    "root": "рут",
    "rootless": "рутлесс",
    "init": "инит",
    "link": "линк",
    "apply": "эплай",
    "running": "раннинг",
    "pending": "пендинг",
    "webhook": "вебхук",
    "webhooks": "вебхуки",
    "hook": "хук",
    "hooks": "хуки",
    "keytab": "кейтаб",
    "agent": "эйджент",
    "mesh": "меш",
    "controller": "контроллер",
    "kill": "килл",
    "ping": "пинг",
    "ps": "пи эс",
    "ss": "эс эс",
    "df": "ди эф",
    "du": "ди ю",
    "uptime": "аптайм",
    "ulimit": "ю лимит",
    "sudoers": "судоерс",
    "xargs": "икс аргс",
    "sigterm": "сиг терм",
    "sigkill": "сиг килл",
    "sighup": "сиг хап",
    "proc": "прок",
    "netstat": "нетстат",
    "guaranteed": "гарантид",
    "burstable": "бёрстабл",
    "besteffort": "бест эффорт",
    "stateful": "стейтфул",
    "stateless": "стейтлесс",
    "best": "бест",
    "practices": "практисес",
    "copy-on-write": "копи он райт",
    "revert": "реверт",
    "reset": "ресет",
    "trunk-based": "транк бейсд",
    "development": "девелопмент",
    "explain": "эксплейн",
    "standalone": "стендэлоун",
    "hard": "хард",
    "soft": "софт",
    "failed": "фейлд",
    "allow_failure": "эллоу фейлюр",
    "admission": "эдмишн",
    "webhook-ом": "вебхуком",
    "lean": "лин",
    "pipe": "пайп",
    "process": "процесс",
    "substitution": "сабститьюшн",
    "forcecommand": "форс команд",
    "rbash": "ар баш",
    "nopasswd": "но пассворд",
    "sticky": "стики",
    "sessions": "сешнс",
    "worker": "воркер",
    "workers": "воркеры",
    "master": "мастер",
    "drain": "дрейн",
    "cordon": "кордон",
    "upgrade": "апгрейд",
    "label": "лейбл",
    "labels": "лейблы",
    "selector": "селектор",
    "annotation": "аннотация",
    # Kubernetes
    "kubernetes": "кубернетес",
    "k8s": "кубер",
    "kubectl": "куб контрол",
    "kubelet": "кублет",
    "kubeadm": "куб адм",
    "kubeconfig": "куб конфиг",
    "kubespray": "кубспрей",
    "kube-proxy": "куб прокси",
    "kube": "куб",
    "apiserver": "эй пи ай сервер",
    "kube-apiserver": "куб эй пи ай сервер",
    "scheduler": "шедулер",
    "controller-manager": "контроллер менеджер",
    "etcd": "е тэ цэ дэ",
    "coredns": "кор дэ эн эс",
    "nodelocal": "нод локал",
    "pod": "под",
    "pods": "поды",
    "node": "нода",
    "nodes": "ноды",
    "deployment": "деплоймент",
    "deployments": "деплойменты",
    "replicaset": "реплика сет",
    "statefulset": "стейтфул сет",
    "daemonset": "демон сет",
    "job": "джоба",
    "cronjob": "крон джоба",
    "service": "сервис",
    "services": "сервисы",
    "ingress": "ингресс",
    "egress": "игресс",
    "configmap": "конфиг мап",
    "configmaps": "конфиг мапы",
    "secret": "секрет",
    "secrets": "секреты",
    "namespace": "неймспейс",
    "namespaces": "неймспейсы",
    "serviceaccount": "сервис аккаунт",
    "rolebinding": "роль биндинг",
    "clusterrole": "кластер роль",
    "clusterrolebinding": "кластер роль биндинг",
    "networkpolicy": "нетворк полиси",
    "endpointslice": "эндпоинт слайс",
    "endpoints": "эндпоинты",
    "persistentvolume": "персистент вольюм",
    "persistentvolumeclaim": "персистент вольюм клейм",
    "storageclass": "сторадж класс",
    "taint": "тейнт",
    "taints": "тейнты",
    "toleration": "толерейшн",
    "tolerations": "толерейшены",
    "affinity": "аффинити",
    "nodeselector": "нод селектор",
    "readiness": "реадинесс",
    "liveness": "лайвнесс",
    "startup": "стартап",
    "probe": "проба",
    "probes": "пробы",
    "crashloopbackoff": "краш луп бэк офф",
    "oomkilled": "у у эм киллд",
    "headless": "хедлесс",
    "clusterip": "кластер ай пи",
    "nodeport": "нод порт",
    "loadbalancer": "лоад балансер",
    "metallb": "метал эл би",
    "hpa": "эйч пи эй",
    "vpa": "ви пи эй",
    "pdb": "пи ди би",
    "qos": "кью о эс",
    "crd": "си ар ди",
    "crds": "си ар ди",
    "cni": "си эн ай",
    "cri": "си ар ай",
    "csi": "си эс ай",
    "calico": "калико",
    "cilium": "силиум",
    "flannel": "фланнел",
    "containerd": "контейнер дэ",
    "cri-o": "край о",
    "runc": "ран си",
    "istio": "истио",
    "envoy": "энвой",
    "linkerd": "линкерди",
    # Контейнеры и сборка
    "docker": "докер",
    "dockerfile": "докер файл",
    "compose": "компоуз",
    "container": "контейнер",
    "containers": "контейнеры",
    "image": "образ",
    "registry": "реджистри",
    "harbor": "харбор",
    "nexus": "нексус",
    "kaniko": "канико",
    "buildkit": "билд кит",
    "buildah": "билда",
    "podman": "подман",
    "dind": "докер ин докер",
    "distroless": "дистролесс",
    "alpine": "алпайн",
    "scratch": "скретч",
    "entrypoint": "энтрипоинт",
    "cmd": "си эм ди",
    "cgroups": "си группы",
    "cgroup": "си группа",
    "overlayfs": "оверлей эф эс",
    "multi-stage": "мульти стейдж",
    # CI/CD и GitOps
    "gitlab": "гитлаб",
    "github": "гитхаб",
    "git": "гит",
    "jenkins": "дженкинс",
    "pipeline": "пайплайн",
    "pipelines": "пайплайны",
    "runner": "раннер",
    "runners": "раннеры",
    "merge": "мёрдж",
    "request": "реквест",
    "pull": "пул",
    "push": "пуш",
    "commit": "коммит",
    "rebase": "рибейз",
    "cherry-pick": "черри пик",
    "argo": "арго",
    "argocd": "арго си ди",
    "flux": "флакс",
    "gitops": "гит опс",
    "helm": "хелм",
    "chart": "чарт",
    "charts": "чарты",
    "values": "вэльюз",
    "kustomize": "кастомайз",
    "applicationset": "эппликейшн сет",
    "canary": "канареечный",
    "rollback": "роллбэк",
    "rollout": "роллаут",
    "deploy": "деплой",
    "release": "релиз",
    "artifact": "артефакт",
    "artifacts": "артефакты",
    "cache": "кэш",
    "needs": "нидс",
    "stage": "стейдж",
    "stages": "стейджи",
    "trivy": "трайви",
    "sonarqube": "сонар кьюб",
    "gitleaks": "гит ликс",
    "smoke": "смоук",
    # IaC
    "terraform": "терраформ",
    "ansible": "ансибл",
    "playbook": "плейбук",
    "playbooks": "плейбуки",
    "inventory": "инвентори",
    "handler": "хэндлер",
    "handlers": "хэндлеры",
    "role": "роль",
    "roles": "роли",
    "tags": "теги",
    "state": "стейт",
    "backend": "бэкенд",
    "provider": "провайдер",
    "module": "модуль",
    "modules": "модули",
    "drift": "дрифт",
    "import": "импорт",
    "pulumi": "пулуми",
    "opentofu": "опен тофу",
    "jinja": "джинджа",
    "jinja2": "джинджа два",
    "host_vars": "хост варс",
    "group_vars": "груп варс",
    "defaults": "дефолтс",
    "vars": "варс",
    "molecule": "молекьюл",
    # Секреты
    "vault": "волт",
    "hashicorp": "хашикорп",
    "injector": "инжектор",
    "sidecar": "сайдкар",
    "external": "экстернал",
    "operator": "оператор",
    "sops": "сопс",
    "keycloak": "кейклоак",
    "oidc": "о ай ди си",
    "ldap": "эл дап",
    # Мониторинг
    "prometheus": "прометеус",
    "grafana": "графана",
    "alertmanager": "алерт менеджер",
    "victoriametrics": "виктория метрикс",
    "vmagent": "ви эм эйджент",
    "thanos": "танос",
    "loki": "локи",
    "promtail": "промтейл",
    "alloy": "аллой",
    "elasticsearch": "эластиксёрч",
    "kibana": "кибана",
    "logstash": "логсташ",
    "fluentd": "флюент ди",
    "fluent": "флюент",
    "bit": "бит",
    "jaeger": "егерь",
    "opentelemetry": "опен телеметри",
    "zabbix": "заббикс",
    "exporter": "экспортер",
    "promql": "пром кью эл",
    "remote_write": "ремоут райт",
    "scrape": "скрейп",
    "dashboard": "дашборд",
    "dashboards": "дашборды",
    "alert": "алерт",
    "alerts": "алерты",
    "sla": "эс эл эй",
    "slo": "эс эл о",
    "sli": "эс эл ай",
    "blackbox": "блэкбокс",
    "rum": "рам",
    # Linux и сеть
    "linux": "линукс",
    "ubuntu": "убунту",
    "debian": "дебиан",
    "centos": "сентос",
    "systemd": "систем ди",
    "systemctl": "систем ктл",
    "journalctl": "джорнал ктл",
    "sshd": "эс эс эйч ди",
    "sudo": "судо",
    "grep": "греп",
    "awk": "авк",
    "sed": "сед",
    "bash": "баш",
    "cron": "крон",
    "crontab": "кронтаб",
    "lsof": "эл соф",
    "strace": "эс трейс",
    "tcpdump": "ти си пи дамп",
    "iostat": "ай о стат",
    "vmstat": "ви эм стат",
    "htop": "эйч топ",
    "top": "топ",
    "inode": "айнод",
    "inodes": "айноды",
    "swap": "своп",
    "zombie": "зомби",
    "load": "лоад",
    "average": "эвередж",
    "iowait": "ай о вейт",
    "iptables": "ай пи тейблс",
    "nftables": "эн эф тейблс",
    "ipvs": "ай пи ви эс",
    "ebpf": "и би пи эф",
    "conntrack": "коннтрак",
    "nginx": "энджинкс",
    "haproxy": "эйч эй прокси",
    "keepalived": "кипэлайвд",
    "traefik": "трэфик",
    "proxy": "прокси",
    "gateway": "гейтвей",
    "lvm": "эл ви эм",
    "raid": "рейд",
    "nfs": "эн эф эс",
    "selinux": "эс и линукс",
    "ext4": "экст четыре",
    "xfs": "икс эф эс",
    "fio": "фио",
    "ndots": "эн дотс",
    "vxlan": "ви экс лан",
    "bgp": "би джи пи",
    "arp": "арп",
    "nat": "нат",
    "vlan": "ви лан",
    "localhost": "локалхост",
    "dig": "диг",
    "curl": "кёрл",
    "wget": "вэ гет",
    "netcat": "нет кэт",
    "mtr": "эм ти ар",
    "traceroute": "трейсроут",
    # Базы и очереди
    "postgresql": "постгрес",
    "postgres": "постгрес",
    "patroni": "патрони",
    "pgbouncer": "пиджи баунсер",
    "mysql": "май эс кью эл",
    "redis": "редис",
    "mongodb": "монго ди би",
    "mongo": "монго",
    "clickhouse": "кликхаус",
    "kafka": "кафка",
    "rabbitmq": "рэббит эм кью",
    "zookeeper": "зукипер",
    "kraft": "крафт",
    "wal": "вал",
    "vacuum": "вакуум",
    "replica": "реплика",
    "cloudnativepg": "клауд нейтив пиджи",
    "s3": "эс три",
    "minio": "минио",
    # Облака и прочее
    "aws": "эй дабл ю эс",
    "gcp": "джи си пи",
    "azure": "ажур",
    "yandex": "яндекс",
    "cloud": "клауд",
    "devops": "девопс",
    "sre": "эс ар и",
    "mlops": "эм эл опс",
    "api": "эй пи ай",
    "rest": "рест",
    "grpc": "джи ар пи си",
    "http": "эйч ти ти пи",
    "https": "эйч ти ти пи эс",
    "json": "джейсон",
    "yaml": "ямл",
    "python": "пайтон",
    "golang": "голанг",
    "java": "джава",
    "jvm": "джей ви эм",
    "heap": "хип",
    "dump": "дамп",
    "oom": "у у эм",
    "killer": "киллер",
    "pr": "пи ар",
    "mr": "эм ар",
    "ci": "си ай",
    "cd": "си ди",
    "ai": "эй ай",
    "llm": "эл эл эм",
    "gpu": "джи пи ю",
    "cpu": "си пи ю",
    "ram": "рам",
    "ssd": "эс эс ди",
    "nvme": "эн ви эм и",
    "iops": "ай опс",
    "ttl": "ти ти эл",
    "tls": "ти эл эс",
    "ssl": "эс эс эл",
    "ssh": "эс эс эйч",
    "dns": "ди эн эс",
    "tcp": "ти си пи",
    "udp": "ю ди пи",
    "ip": "ай пи",
    "url": "ю ар эл",
    "vm": "ви эм",
    "vms": "ви эм",
    "pid": "пид",
    "rbac": "эр бак",
    "mtls": "эм ти эл эс",
    "jwt": "джей дабл ю ти",
    "ok": "окей",
    "timeout": "таймаут",
    "retry": "ретрай",
    "backoff": "бэкофф",
    "staging": "стейджинг",
    "prod": "прод",
    "production": "продакшн",
    "dev": "дев",
    "test": "тест",
    "debug": "дебаг",
    "bug": "баг",
    "feature": "фича",
    "flag": "флаг",
    "flags": "флаги",
    "on-call": "он колл",
    "postmortem": "постмортем",
    "runbook": "ранбук",
    "health": "хелс",
    "check": "чек",
    "checks": "чеки",
    "rate": "рейт",
    "limit": "лимит",
    "limits": "лимиты",
    "requests": "реквесты",
    "latency": "латенси",
    "throughput": "сру пут",
    "burn": "бёрн",
    "budget": "бюджет",
    "split-brain": "сплит брейн",
    "failover": "фейловер",
    "switchover": "свитчовер",
    "backup": "бэкап",
    "backups": "бэкапы",
    "restore": "ресторе",
    "snapshot": "снапшот",
    # Python / web / SQL (вопросы по Python-трекам)
    "sqlite": "эс кью лайт",
    "sqlalchemy": "эс кью эл алхими",
    "airflow": "эйрфлоу",
    "django": "джанго",
    "fastapi": "фаст эй пи ай",
    "flask": "фласк",
    "celery": "селери",
    "apache": "апач",
    "pytest": "пай тест",
    "numpy": "нам пай",
    "asyncio": "асинк ай о",
    "async": "асинк",
    "await": "эвейт",
    "middleware": "мидлвар",
    "event": "ивент",
    "loop": "луп",
    "websocket": "вебсокет",
    "websockets": "вебсокеты",
    "raft": "рафт",
    "drf": "ди ар эф",
    "orm": "о ар эм",
    "asgi": "эй эс джи ай",
    "wsgi": "ви эс джи ай",
    "sql": "эс кью эл",
    "cte": "си ти и",
    "gil": "гил",
    "dag": "даг",
    "dlx": "ди эл экс",
    "rpc": "ар пи си",
    "vpn": "ви пи эн",
    "join": "джойн",
    "select": "селект",
    "insert": "инсерт",
    "update": "апдейт",
    "delete": "дилит",
    "where": "вэр",
    "group": "груп",
    "dict": "дикт",
    "list": "лист",
    "set": "сет",
    "tuple": "тупл",
    "frozenset": "фрозенсет",
    "lambda": "лямбда",
    "none": "нан",
    "true": "тру",
    "false": "фолс",
    "def": "деф",
    "return": "ретёрн",
    "vs": "против",
    # Слова из реальных вопросов, которые транслитерация читает плохо
    "manager": "менеджер",
    "managed": "менеджд",
    "space": "спейс",
    "device": "девайс",
    "downtime": "даунтайм",
    "recreate": "рекриэйт",
    "template": "темплейт",
    "define": "дефайн",
    "include": "инклюд",
    "application": "эпликейшн",
    "claude": "клод",
    "dora": "дора",
    "run": "ран",
    "runtime": "рантайм",
    "error": "эррор",
    "plane": "плейн",
    "idle": "айдл",
    "bare": "бэр",
    "healthy": "хелси",
    "upstream": "апстрим",
    "exit": "экзит",
    "schedule": "скеджул",
    "unschedulable": "анскеджулабл",
    "dedicated": "дедикейтед",
    "refused": "рефьюзд",
    "files": "файлс",
    "free": "фри",
    "umount": "ю маунт",
    "builtin": "билтин",
    "kind": "кайнд",
    "security": "секьюрити",
    "user": "юзер",
    "as": "эз",
    "synced": "синкт",
    "statements": "стейтментс",
    "mac": "мак",
    "static": "статик",
    "available": "эвейлабл",
    "upload": "аплоад",
}

# Названия английских букв для аббревиатур, которых нет в словаре
LETTERS: Final[dict[str, str]] = {
    "a": "эй",
    "b": "би",
    "c": "си",
    "d": "ди",
    "e": "и",
    "f": "эф",
    "g": "джи",
    "h": "эйч",
    "i": "ай",
    "j": "джей",
    "k": "кей",
    "l": "эл",
    "m": "эм",
    "n": "эн",
    "o": "о",
    "p": "пи",
    "q": "кью",
    "r": "ар",
    "s": "эс",
    "t": "ти",
    "u": "ю",
    "v": "ви",
    "w": "дабл ю",
    "x": "экс",
    "y": "уай",
    "z": "зед",
}

# Простые правила чтения английских слов (сначала сочетания, потом буквы)
_COMBOS: Final[list[tuple[str, str]]] = [
    ("tion", "шн"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("th", "т"),
    ("ph", "ф"),
    ("ck", "к"),
    ("qu", "кв"),
    ("oo", "у"),
    ("ee", "и"),
    ("ea", "и"),
    ("ou", "ау"),
    ("ow", "оу"),
    ("ai", "эй"),
    ("ay", "эй"),
    ("oa", "оу"),
    ("ie", "и"),
    ("er", "ер"),
    ("wh", "в"),
    ("kn", "н"),
    ("ng", "нг"),
    ("x", "кс"),
    ("j", "дж"),
]
_LETTER_RU: Final[dict[str, str]] = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "y": "и",
    "z": "з",
}

_WORD_RE: Final = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*[A-Za-z0-9]|[A-Za-z]")


def _translit(word: str) -> str:
    """Transliterate an English word into Cyrillic by simple reading rules."""
    w = word.lower()
    if w.endswith("e") and len(w) > 3:  # немая e на конце: release, image
        w = w[:-1]
    out: list[str] = []
    i = 0
    while i < len(w):
        for src, dst in _COMBOS:
            if w.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            ch = w[i]
            if ch == "c" and i + 1 < len(w) and w[i + 1] in "eiy":
                out.append("с")
            elif ch.isalpha():
                out.append(_LETTER_RU.get(ch, ""))
            elif ch.isdigit():
                out.append(ch)
            else:
                out.append(" ")
            i += 1
    return "".join(out)


def _spell(word: str) -> str:
    """Spell a word letter by letter using English letter names."""
    return " ".join(LETTERS.get(c, c) for c in word.lower() if c.isalnum())


def _speak_word(word: str) -> str:
    """Return the Russian pronunciation of one Latin word."""
    key = word.lower()
    if key in RU_TERMS:
        return RU_TERMS[key]
    # составные через дефис или подчёркивание: каждую часть отдельно
    parts = re.split(r"[-_]", word)
    if len(parts) > 1:
        return " ".join(_speak_word(p) for p in parts if p)
    # CamelCase и склейки вроде DNSCache: делим на части
    camel = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", word)
    if len(camel) > 1:
        return " ".join(_speak_word(p) for p in camel)
    if word.isupper() and len(word) <= 5:  # аббревиатура: по буквам
        return _spell(word)
    if not re.search(r"[aeiouy]", key):  # без гласных не прочитать — по буквам
        return _spell(word)
    return _translit(word)


_RU_UNITS: Final[tuple[str, ...]] = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_RU_TENS: Final[tuple[str, ...]] = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_RU_HUNDREDS: Final[tuple[str, ...]] = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)
# (singular, few, many) forms and grammatical gender of each scale word.
_RU_SCALES: Final[tuple[tuple[tuple[str, str, str], bool], ...]] = (
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
)
_RU_MAX_SPELLED: Final = 999_999_999
_NUMBER_PATTERN: Final = re.compile(r"\d+(?:[.,]\d+)?")


def _ru_plural(count: int, forms: tuple[str, str, str]) -> str:
    """Pick the Russian plural form agreeing with ``count``."""
    if count % 100 in range(11, 15):
        return forms[2]
    last = count % 10
    if last == 1:
        return forms[0]
    if last in (2, 3, 4):
        return forms[1]
    return forms[2]


def _ru_triplet(value: int, feminine: bool) -> list[str]:
    """Spell a number in ``1..999`` as Russian words."""
    words: list[str] = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        words.append(_RU_HUNDREDS[hundreds])
    if rest >= 20:
        tens, rest = divmod(rest, 10)
        words.append(_RU_TENS[tens])
    if rest:
        unit = _RU_UNITS[rest]
        if feminine and rest in (1, 2):
            unit = "одна" if rest == 1 else "две"
        words.append(unit)
    return words


def _ru_integer(digits: str) -> str:
    """Spell a run of digits as a Russian cardinal number.

    Leading zeros and numbers above the spelled range are read digit by digit
    (version strings, ids, ports with leading zeros).
    """
    value = int(digits)
    if value > _RU_MAX_SPELLED or (len(digits) > 1 and digits.startswith("0")):
        return " ".join(_RU_UNITS[int(digit)] for digit in digits)
    if value == 0:
        return _RU_UNITS[0]
    words: list[str] = []
    millions, rest = divmod(value, 1_000_000)
    thousands, units = divmod(rest, 1000)
    for count, (forms, feminine) in (
        (millions, _RU_SCALES[1]),
        (thousands, _RU_SCALES[0]),
    ):
        if count:
            words.extend(_ru_triplet(count, feminine))
            words.append(_ru_plural(count, forms))
    if units:
        words.extend(_ru_triplet(units, feminine=False))
    return " ".join(words)


def _ru_number(match: re.Match[str]) -> str:
    """Spell a matched integer or decimal (``3.12`` / ``0,5``) in Russian."""
    token = match.group(0)
    parts = re.split(r"[.,]", token)
    spoken = " точка ".join(_ru_integer(part) for part in parts)
    source = match.string
    if match.start() > 0 and source[match.start() - 1].isalpha():
        spoken = " " + spoken
    if match.end() < len(source) and source[match.end()].isalpha():
        spoken += " "
    return spoken


def _ru_latin_to_speech(text: str) -> str:
    """Replace Latin words in ``text`` with their Russian pronunciation."""
    text = text.replace("CI/CD", "си ай си ди").replace("ci/cd", "си ай си ди")
    text = text.replace("I/O", "ай о").replace("/", " ")
    return _WORD_RE.sub(lambda m: _speak_word(m.group(0)), text)


def apply_term_substitutions(text: str, locale: str) -> str:
    """Prepare question text for speech synthesis in ``locale``.

    For Russian, Latin terms are rewritten in Cyrillic and numbers are spelled
    out (the Silero Russian token set has neither Latin letters nor digits, so
    ``"3 причины в Kubernetes"`` would otherwise be read as ``"причины в"``).
    Numbers read in the nominative case — cases are not inflected.

    Args:
        text: Raw question text snapshot.
        locale: Interview locale code; other locales return text unchanged.

    Returns:
        Text prepared for synthesis.
    """
    if locale != "ru":
        return text
    text = _ru_latin_to_speech(text)
    return _NUMBER_PATTERN.sub(_ru_number, text)
