#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 entrosana
"""MCP-Server für lp21.py — der Lehrplan 21 als Werkzeug für Sprachmodelle.

Herausgeber: entrosana · https://github.com/entrosana/hub
Lizenz: AGPL-3.0-or-later, siehe LICENSE.

Warum es diesen Server gibt: lp21.py liefert Kompetenzcode, Wortlaut und
belastbare Quellenangabe. Gebraucht wird das mitten im Schreiben, nicht davor.
Über die Kommandozeile muss ein Mensch aufrufen und einfügen; über MCP holt
sich das Modell die Stelle selbst, während es plant, formuliert oder prüft.

Bauform: Wie lp21.py kommt auch dieser Server mit der Standardbibliothek aus.
Kein SDK, keine Installation, kein virtuelles Umfeld — die Datei genügt. Das
Protokoll ist JSON-RPC 2.0 über stdin/stdout, zeilenweise.

Wichtig für die Wartung: stdout gehört dem Protokoll. lp21.py schreibt seine
Ergebnisse aber mit print(). Jeder Aufruf läuft deshalb unter
contextlib.redirect_stdout; ohne das würde die erste Ausgabe den Datenstrom
zerstören. Meldungen dieses Servers gehen nach stderr.

Zu den Inhalten: Dieser Server liefert keinen Lehrplantext mit. Er liest den
Index, den lp21.py auf dem eigenen Rechner aufgebaut hat. Die Rechte an den
Inhalten liegen bei der Erziehungsdirektion des Kantons Bern beziehungsweise
der D-EDK.
"""

import contextlib
import io
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lp21  # noqa: E402  — erst nach dem Pfad, absichtlich

SERVER_NAME = 'lp21'
SERVER_VERSION = '1.0.0'

# Neueste zuerst. Fragt die Gegenstelle eine Fassung an, die hier steht, wird
# genau diese bestätigt; sonst die neueste, die dieser Server beherrscht.
UNTERSTUETZTE_FASSUNGEN = ('2025-06-18', '2025-03-26', '2024-11-05')


def melde(text):
    """Nach stderr, niemals nach stdout — dort läuft das Protokoll."""
    sys.stderr.write('[lp21-mcp] %s\n' % text)
    sys.stderr.flush()


# ------------------------------------------------------------- Werkzeuge

# «export» fehlt hier bewusst: der Befehl schreibt den gesamten Bestand als
# Markdown auf die Platte. Das ist eine Massenausleitung fremdrechtlich
# gebundener Inhalte und gehört in eine bewusste Handbewegung auf der
# Kommandozeile, nicht in ein Werkzeug, das ein Modell nebenbei auslösen kann.
WERKZEUGE = [
    {
        'name': 'lp21_status',
        'description': (
            'Prüft, ob der Lehrplan-Index auf diesem Rechner vorhanden und '
            'vollständig ist. Ohne Index arbeitet nur lp21_index. Immer '
            'zuerst aufrufen, wenn ein anderer Aufruf «Index fehlt» meldet.'),
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'befehl': 'status',
        'baue': lambda a: [],
    },
    {
        'name': 'lp21_index',
        'description': (
            'Baut den Index einmalig auf, indem be.lehrplan.ch abgerufen wird. '
            'Läuft rund acht Minuten: etwa 474 Seiten mit 0,4 s Abstand. '
            'ACHTUNG: «praefix» macht den Lauf NICHT kürzer. Der Kompetenzcode '
            'steht nicht in der Seitenadresse, sondern erst auf der Seite — '
            'gefiltert wird deshalb erst nach dem Abruf. Ein Präfix begrenzt '
            'nur, was gespeichert wird, und erspart der Quelle keinen einzigen '
            'Abruf. Braucht als einziges Werkzeug eine Netzverbindung. Wegen '
            'der Laufzeit gehört der erste Aufbau auf die Kommandozeile, nicht '
            'hierher.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'praefix': {
                    'type': 'array', 'items': {'type': 'string'},
                    'description': ('Fachbereichskürzel, auf die der gespeicherte '
                                    'Index eingeschränkt wird. Leer = alles. Spart '
                                    'KEINE Abrufe und keine Zeit.')},
                'frisch': {
                    'type': 'boolean',
                    'description': 'Zwischenspeicher umgehen und neu abrufen.'},
            },
            'additionalProperties': False,
        },
        'befehl': 'index',
        'baue': lambda a: list(a.get('praefix') or []) + (['--frisch'] if a.get('frisch') else []),
    },
    {
        'name': 'lp21_zeige',
        'description': (
            'Gibt eine Kompetenz vollständig aus: Titel, Pfad im Lehrplan, '
            'Handlungsaspekt, alle Kompetenzstufen mit Zyklus und Wortlaut, '
            'verbindliche Inhalte, Querverweise und den stabilen Permalink. '
            'Das ist der Befehl für «was steht da genau».'),
        'inputSchema': {
            'type': 'object',
            'properties': {'code': {
                'type': 'string',
                'description': 'Kompetenzcode, z. B. ERG.5.6 oder MA.1.A.3'}},
            'required': ['code'], 'additionalProperties': False,
        },
        'befehl': 'zeige',
        'baue': lambda a: [a['code']],
    },
    {
        'name': 'lp21_zitat',
        'description': (
            'Liefert die fertige Quellenangabe zu einer Kompetenz oder einer '
            'einzelnen Kompetenzstufe, nach der amtlichen Zitierhilfe, samt '
            'Permalink. Immer dieses Werkzeug verwenden, wenn eine Fundstelle '
            'belegt werden soll — die Angabe niemals selbst formulieren.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'code': {
                'type': 'string',
                'description': 'Code, wahlweise mit Stufe: ERG.5.6 oder ERG.5.6.d'}},
            'required': ['code'], 'additionalProperties': False,
        },
        'befehl': 'zitat',
        'baue': lambda a: [a['code']],
    },
    {
        'name': 'lp21_suche',
        'description': (
            'Volltextsuche über Kompetenztitel, Kompetenzstufen und die '
            'überfachlichen Kompetenzen. Der Einstieg, wenn der Code noch '
            'nicht bekannt ist: erst suchen, dann mit lp21_zeige vertiefen.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'text': {
                'type': 'string', 'description': 'Suchbegriff, z. B. Konflikt'}},
            'required': ['text'], 'additionalProperties': False,
        },
        'befehl': 'suche',
        'baue': lambda a: [a['text']],
    },
    {
        'name': 'lp21_baum',
        'description': (
            'Zeigt die Gliederung nach Fachbereich und Kompetenzbereich. Ohne '
            'Angabe die oberste Ebene, mit Präfix der Ausschnitt darunter. '
            'Nützlich, um sich zu orientieren, bevor gesucht wird.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'praefix': {
                'type': 'string',
                'description': 'Ausschnitt, z. B. MA oder MA.1. Leer = oberste Ebene.'}},
            'additionalProperties': False,
        },
        'befehl': 'baum',
        'baue': lambda a: [a['praefix']] if a.get('praefix') else [],
    },
    {
        'name': 'lp21_ueberfachlich',
        'description': (
            'Die überfachlichen Kompetenzen, die im Lehrplan keinen Code '
            'tragen — personale, soziale und methodische. Ohne Angabe alle, '
            'mit Text gefiltert.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'text': {
                'type': 'string', 'description': 'Filterbegriff. Leer = alle Gruppen.'}},
            'additionalProperties': False,
        },
        'befehl': 'ueberfachlich',
        'baue': lambda a: [a['text']] if a.get('text') else [],
    },
    {
        'name': 'lp21_pruefe',
        'description': (
            'Prüft eine .docx- oder .md-Datei: schlägt jeden darin genannten '
            'Kompetenzcode nach und vergleicht jedes «…»-Zitat mit dem '
            'Wortlaut im Lehrplan. Meldet erfundene Codes und abweichende '
            'Zitate. Der Befehl, mit dem sich eine Behauptung belegen lässt, '
            'statt sie zu glauben.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'datei': {
                'type': 'string',
                'description': 'Pfad zur .docx- oder .md-Datei auf diesem Rechner'}},
            'required': ['datei'], 'additionalProperties': False,
        },
        'befehl': 'pruefe',
        'baue': lambda a: [a['datei']],
    },
]

NACH_NAME = dict((w['name'], w) for w in WERKZEUGE)


def werkzeugliste():
    """Die Liste für tools/list — ohne die internen Felder."""
    return [{'name': w['name'], 'description': w['description'],
             'inputSchema': w['inputSchema']} for w in WERKZEUGE]


class UnbekanntesWerkzeug(Exception):
    """Der Name aus tools/call steht nicht in WERKZEUGE."""


class FehlendesFeld(Exception):
    """Ein als required deklariertes Feld fehlt im Aufruf.

    Bewusst eine eigene Klasse: früher fiel das mit dem KeyError des
    Argumentaufbaus zusammen und wurde als «Methode nicht gefunden»
    beantwortet. Das Modell konnte daraus nicht lernen, was zu tun ist.
    """


def rufe_werkzeug(name, args):
    """Führt einen lp21-Befehl aus und gibt seine Ausgabe als Text zurück.

    Der Kern schreibt mit print(). Weil stdout hier dem Protokoll gehört, wird
    er für die Dauer des Aufrufs umgeleitet. Der Rückgabewert des Befehls
    entscheidet, ob das Ergebnis als Fehler gilt: lp21 nutzt 0 für Erfolg.
    """
    w = NACH_NAME.get(name)
    if w is None:
        raise UnbekanntesWerkzeug(
            'Es gibt kein Werkzeug «%s». Vorhanden sind: %s.'
            % (name, ', '.join(sorted(NACH_NAME))))

    args = args or {}
    fehlt = [f for f in w['inputSchema'].get('required', []) if not args.get(f)]
    if fehlt:
        raise FehlendesFeld(
            'Dem Aufruf von %s fehlt: %s. Erwartet werden: %s.'
            % (name, ', '.join(fehlt),
               ', '.join(sorted(w['inputSchema'].get('properties', {}))) or '—'))

    funktion = getattr(lp21, 'befehl_' + w['befehl'])
    argumente = w['baue'](args)

    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        rc = funktion(argumente)
    text = puffer.getvalue().strip()

    if not text:
        text = '(keine Ausgabe)'
    fehler = isinstance(rc, int) and rc != 0
    return text, fehler


# ------------------------------------------------------------- Protokoll

def antwort(rid, ergebnis):
    return {'jsonrpc': '2.0', 'id': rid, 'result': ergebnis}


def fehlerantwort(rid, code, nachricht):
    return {'jsonrpc': '2.0', 'id': rid, 'error': {'code': code, 'message': nachricht}}


def verteile(anfrage):
    """Beantwortet eine JSON-RPC-Nachricht. None heisst: keine Antwort senden."""
    methode = anfrage.get('method')
    rid = anfrage.get('id')
    params = anfrage.get('params') or {}

    if methode == 'initialize':
        gewuenscht = params.get('protocolVersion')
        fassung = gewuenscht if gewuenscht in UNTERSTUETZTE_FASSUNGEN else UNTERSTUETZTE_FASSUNGEN[0]
        return antwort(rid, {
            'protocolVersion': fassung,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
        })

    # Benachrichtigungen tragen keine id und werden nicht beantwortet.
    if methode == 'notifications/initialized':
        return None

    if methode == 'ping':
        return antwort(rid, {})

    if methode == 'tools/list':
        return antwort(rid, {'tools': werkzeugliste()})

    if methode == 'tools/call':
        name = params.get('name')
        args = params.get('arguments') or {}
        try:
            text, fehler = rufe_werkzeug(name, args)
            return antwort(rid, {'content': [{'type': 'text', 'text': text}],
                                 'isError': fehler})
        except UnbekanntesWerkzeug as e:
            return fehlerantwort(rid, -32601, str(e))
        except FehlendesFeld as e:
            # Als Werkzeugfehler, nicht als Protokollfehler: so bekommt das
            # Modell den Satz im Wortlaut zurück und kann den Aufruf berichtigen.
            return antwort(rid, {'content': [{'type': 'text', 'text': str(e)}],
                                 'isError': True})
        except Exception as e:
            melde('Werkzeug %r gescheitert: %s\n%s' % (name, e, traceback.format_exc()))
            # Ein abgestuerztes Werkzeug ist kein Protokollfehler: das Modell
            # soll die Ursache lesen und es anders versuchen koennen.
            return antwort(rid, {
                'content': [{'type': 'text',
                             'text': '%s: %s' % (type(e).__name__, e)}],
                'isError': True})

    # Dieser Server bietet weder Ressourcen noch Vorlagen an; leere Listen
    # sind die richtige Antwort, damit die Gegenstelle nicht in einen Fehler
    # laeuft, nur weil sie danach fragt.
    if methode in ('resources/list', 'resources/templates/list', 'prompts/list'):
        schluessel = 'resourceTemplates' if methode.endswith('templates/list') \
            else methode.split('/')[0]
        return antwort(rid, {schluessel: []})

    if rid is not None:
        return fehlerantwort(rid, -32601, 'unbekannte Methode: %s' % methode)
    return None


def hauptschleife():
    """Zeilenweise JSON über stdin/stdout, bis die Gegenstelle schliesst."""
    eingabe = sys.stdin
    for zeile in eingabe:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            anfrage = json.loads(zeile)
        except ValueError as e:
            melde('unlesbare Zeile verworfen: %s' % e)
            continue

        # Ein Stapel mehrerer Nachrichten ist zulässig.
        stapel = anfrage if isinstance(anfrage, list) else [anfrage]
        for einzeln in stapel:
            try:
                erg = verteile(einzeln)
            except Exception as e:
                melde('Verteiler gescheitert: %s\n%s' % (e, traceback.format_exc()))
                erg = fehlerantwort(einzeln.get('id'), -32603, str(e))
            if erg is None:
                continue
            try:
                # Ein einzelnes Surrogat — etwa aus einem kaputt kodierten
                # Dateinamen — liesse sich nicht nach UTF-8 schreiben und
                # beendete den ganzen Prozess. Für einen stdio-Server heisst
                # das: die Gegenstelle verliert das Werkzeug für die restliche
                # Sitzung. Lieber ein ersetztes Zeichen als ein toter Server.
                zeile = json.dumps(erg, ensure_ascii=False)
                zeile = zeile.encode('utf-8', 'replace').decode('utf-8')
                sys.stdout.write(zeile + '\n')
                sys.stdout.flush()
            except BrokenPipeError:
                return
            except UnicodeEncodeError as e:
                melde('Antwort nicht schreibbar: %s' % e)


def main():
    # lp21.py stellt stdout beim Import auf UTF-8; für das Protokoll ist das
    # richtig, hier nur noch stderr nachziehen.
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    melde('bereit — %s %s, Index: %s' % (
        SERVER_NAME, SERVER_VERSION,
        'vorhanden' if os.path.exists(lp21.INDEX) else 'FEHLT, zuerst lp21_index aufrufen'))
    try:
        hauptschleife()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
