#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 entrosana
"""Zitier- und Navigierhilfe für den Lehrplan 21, Kantonsfassung Bern.

Quelle: be.lehrplan.ch. Nur Standardbibliothek, keine Abhängigkeiten.
Aufruf: python lp21.py <befehl> [...]   ·   python lp21.py hilfe

Herausgeber: entrosana · https://github.com/entrosana/hub
Lizenz des Codes: AGPL-3.0-or-later, siehe LICENSE.

Zu den Inhalten: Dieses Werkzeug liefert keinen Lehrplantext mit. Es baut den
Index beim ersten Lauf selbst auf, indem es be.lehrplan.ch abruft. Die Rechte
an den Inhalten des Lehrplans 21 liegen bei der Erziehungsdirektion des
Kantons Bern beziehungsweise der D-EDK, nicht bei entrosana. Wer die so
gewonnenen Inhalte weitergeben oder in ein Angebot einbauen will, braucht
deren Erlaubnis — dieses Skript erteilt sie nicht und ersetzt sie nicht.
"""

import sys, os, re, json, html, time, zipfile
import urllib.parse, urllib.request, urllib.error

BASIS = 'https://be.lehrplan.ch'
HIER = os.path.dirname(os.path.abspath(__file__))


def cache_ort():
    """Zwischenspeicher bewusst ausserhalb des Skriptordners.

    Der Skriptordner kann unter Versionsverwaltung stehen oder zwischen
    Rechnern abgeglichen werden. Die rohen HTML-Seiten sind Arbeitsmaterial
    und gehören in keines von beidem; der Index trägt alles, was die
    Lesebefehle brauchen.

    Der Ort liegt im Benutzerordner und nicht unter LOCALAPPDATA, weil die
    Store-Fassung von Python Zugriffe auf AppData\\Local in einen eigenen
    Container umleitet. Sonst liegt der Zwischenspeicher je nach aufgerufenem
    Interpreter woanders, ohne dass es auffällt.
    """
    if os.environ.get('LP21_CACHE'):
        return os.environ['LP21_CACHE']
    if os.environ.get('XDG_CACHE_HOME'):
        return os.path.join(os.environ['XDG_CACHE_HOME'], 'lp21')
    return os.path.join(os.path.expanduser('~'), '.lp21', 'cache')


CACHE = cache_ort()
INDEX = os.path.join(HIER, 'index.json')
UEFA = os.path.join(HIER, 'ueberfachlich.json')
UEFA_CODE = 'e|200|3'
# Mindestabstand zwischen zwei Abrufen, in Sekunden. Über LP21_PAUSE höher zu
# setzen, wenn die Quelle es verlangt — niedriger zu setzen ist unhöflich.
PAUSE = float(os.environ.get('LP21_PAUSE') or 0.4)
# Kennung gegenüber be.lehrplan.ch. Sie nennt den Herausgeber und einen Weg,
# ihn zu erreichen — wer den Abruf sieht, soll wissen, wen er ansprechen kann.
# Wer das Werkzeug im eigenen Namen betreibt, setzt LP21_UA auf die eigene
# Kennung; sonst laufen fremde Abrufe unter dem Namen von entrosana.
UA = (os.environ.get('LP21_UA')
      or 'lp21.py Zitierpruefung (entrosana; +https://github.com/entrosana/hub)')
# Wiederholungen je Abruf, bevor aufgegeben wird.
VERSUCHE = 4

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# ---------------------------------------------------------------- Abruf

class AbrufFehler(Exception):
    """Ein Abruf ist endgültig gescheitert.

    Trägt eine Meldung, die einem Menschen sagt, was zu tun ist. Sie ersetzt
    den rohen Traceback, den ein Netzausfall vorher an dieser Stelle warf.
    """


# Zeitpunkt des letzten Abrufs, für den Mindestabstand.
_letzter_abruf = [0.0]


def _warte():
    """Mindestabstand vor dem nächsten Abruf einhalten.

    Der Abstand wird VOR dem Abruf genommen, nicht danach. Vorher stand die
    Pause am Ende der Abruffunktion und fiel bei jeder Ausnahme aus — also
    genau dann, wenn die Quelle ohnehin schon drosselt oder klemmt.
    """
    rest = PAUSE - (time.time() - _letzter_abruf[0])
    if rest > 0:
        time.sleep(rest)
    _letzter_abruf[0] = time.time()


def hole(code, frisch=False):
    """Seite zu einem index.php-Code holen, mit Zwischenspeicher auf Platte.

    Wiederholt bei vorübergehenden Störungen mit wachsendem Abstand. Sagt die
    Quelle über Retry-After selbst, wie lange sie in Ruhe gelassen werden will,
    hat diese Angabe Vorrang vor der eigenen Wartezeit.
    """
    os.makedirs(CACHE, exist_ok=True)
    name = re.sub(r'[^A-Za-z0-9]', '_', code) or 'startseite'
    datei = os.path.join(CACHE, name + '.html')
    if not frisch and os.path.exists(datei) and os.path.getsize(datei) > 2000:
        with open(datei, encoding='utf-8') as f:
            return f.read()
    url = BASIS + '/index.php'
    if code:
        url += '?code=' + urllib.parse.quote(code, safe='|')
    req = urllib.request.Request(url, headers={'User-Agent': UA})

    letzter = 'unbekannt'
    for versuch in range(1, VERSUCHE + 1):
        _warte()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = r.read().decode('utf-8', 'replace')
            break
        except urllib.error.HTTPError as e:
            letzter = 'HTTP %s' % e.code
            if e.code in (429, 503):
                nach = e.headers.get('Retry-After') if e.headers else None
                try:
                    # Gedeckelt, damit ein absurder Wert den Lauf nicht anhält.
                    time.sleep(min(float(nach), 120))
                except (TypeError, ValueError):
                    time.sleep(PAUSE * 2 ** versuch)
                continue
            if 500 <= e.code < 600:
                time.sleep(PAUSE * 2 ** versuch)
                continue
            # 4xx ausser 429: die Anfrage selbst stimmt nicht, Wiederholen hilft nicht.
            raise AbrufFehler('%s antwortet mit HTTP %s auf «%s».'
                              % (BASIS, e.code, code or 'Startseite'))
        except urllib.error.URLError as e:
            letzter = str(e.reason)
            time.sleep(PAUSE * 2 ** versuch)
        except OSError as e:
            letzter = str(e)
            time.sleep(PAUSE * 2 ** versuch)
    else:
        raise AbrufFehler(
            '%s ist nach %d Versuchen nicht erreichbar (%s). Netzverbindung '
            'prüfen und «index» erneut starten — der Zwischenspeicher behält, '
            'was bereits geholt wurde.' % (BASIS, VERSUCHE, letzter))

    with open(datei, 'w', encoding='utf-8') as f:
        f.write(d)
    return d


def schreibe_json(pfad, daten, **kw):
    """Erst in eine Nebendatei schreiben, dann an die Stelle rücken.

    Ein Abbruch mitten im Schreiben zerstörte vorher die vorhandene Datei. Bei
    index.json sind das 880 kB, die nur ein neuer Volllauf zurückbringt.
    os.replace ist innerhalb eines Dateisystems unteilbar.
    """
    neben = pfad + '.neu'
    try:
        with open(neben, 'w', encoding='utf-8') as f:
            json.dump(daten, f, **kw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(neben, pfad)
    except BaseException:
        # Auch bei Strg-C soll keine halbe Nebendatei liegen bleiben.
        try:
            os.remove(neben)
        except OSError:
            pass
        raise


def text(s):
    """Auszeichnung entfernen, Entities auflösen, Leerraum normalisieren."""
    s = re.sub(r'(?s)<(script|style).*?</\1>', ' ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    # Weiche Trennstriche und Nullbreite-Leerzeichen sitzen mitten in den
    # Wörtern der Quelle. Bleiben sie stehen, schlägt jeder Zeichenvergleich
    # fehl, obwohl das Zitat stimmt.
    s = s.replace('­', '').replace('​', '').replace('﻿', '')
    return ' '.join(s.split())


def ohne_begriffe(roh):
    """Randbegriffe («Verbindliche Inhalte») vom Kompetenzwortlaut trennen."""
    begriffe = [text(m) for m in re.findall(r'<span[^>]*class="[^"]*begriffe[^"]*"[^>]*>(.*?)</span>',
                                            roh, re.S)]
    return re.sub(r'(?s)<span[^>]*class="[^"]*begriffe[^"]*"[^>]*>.*?</span>', '', roh), begriffe


def block(d, klasse, ab=0):
    """Inhalt des ersten div mit dieser Klasse ab Position `ab`, grob geklammert."""
    m = re.search(r'<div[^>]*class="[^"]*' + klasse + r'[^"]*"[^>]*>', d[ab:])
    if not m:
        return None, -1
    start = ab + m.end()
    tiefe, i = 1, start
    for t in re.finditer(r'<(/?)div\b', d[start:]):
        tiefe += -1 if t.group(1) else 1
        if tiefe == 0:
            i = start + t.start()
            break
    return d[start:i], i


# ---------------------------------------------------------------- Parser

def lies_kompetenz(d, quelle=''):
    """Detailseite in ein Datenobjekt überführen. Wirft bei fehlendem Code."""
    mc = re.search(r'font_ganzercode"[^>]*>([^<]+)<', d)
    if not mc:
        raise ValueError('kein Kompetenzcode auf der Seite %s' % quelle)
    code = html.unescape(mc.group(1)).strip()

    roh, _ = block(d, 'kompetenztitel')
    titel = ''
    if roh:
        teile = re.findall(r'<p(?![^>]*komptitelnr)[^>]*>(.*?)</p>', roh, re.S)
        if teile:
            titel = text(teile[-1])

    perma = ''
    mp = re.search(r'id="(101[A-Za-z0-9]{10,})\.u\d+"', d)
    if mp:
        perma = BASIS + '/' + mp.group(1)

    krumen = []
    mb = re.search(r'(?s)<div id="breadcrumb".*?</div>', d)
    if mb:
        krumen = [text(x) for x in re.findall(r'<a[^>]*>(.*?)</a>', mb.group(0), re.S)]
        krumen = [k for k in krumen if k and k != 'Startseite']

    ma = re.search(r'aufbauten_zwischentitel[^"]*"[^>]*>(.*?)</div>', d, re.S)
    aspekt = text(ma.group(1)) if ma else ''

    stufen, pos = [], 0
    while True:
        m = re.search(r'komp_cell kompetenz_lit"[^>]*title="([^"]+)"', d[pos:])
        if not m:
            break
        scode = html.unescape(m.group(1)).strip()
        pos += m.end()
        vor = d[:pos]
        mz = None
        for mz in re.finditer(r'class="zycode">\s*(\d+)', vor):
            pass
        zyklus = mz.group(1) if mz else ''
        roh, ende = block(d, 'kompetenz_text', pos)
        rein, begriffe = ohne_begriffe(roh or '')
        zeilen = [text(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', rein, re.S)]
        zeilen = [z for z in zeilen if z]
        qroh, _ = block(d, 'kompetenz_querverw', pos)
        quer = [text(x) for x in re.findall(r'<a[^>]*>(.*?)</a>', qroh or '', re.S)]
        stufen.append({'code': scode, 'zyklus': zyklus, 'buchstabe': scode.split('.')[-1],
                       'text': zeilen, 'begriffe': begriffe,
                       'querverweise': [q for q in quer if q]})
        pos = max(pos, ende if ende > 0 else pos)

    def eck(schluessel):
        # Vorangehende stehen in div.eck, Nachfolgende in div.bottomeck.
        codes = []
        for m in re.finditer(r'(?s)<div class="(?:bottom)?eck">(.*?)</div></div>', d):
            roh = m.group(1)
            if schluessel in roh:
                codes += re.findall(r'<a[^>]*title="([^"]+)"', roh)
        return codes

    return {'code': code, 'titel': titel, 'permalink': perma, 'pfad': krumen,
            'handlungsaspekt': aspekt, 'stufen': stufen,
            'vorangehend': eck('Vorangehende'), 'nachfolgend': eck('Nachfolgende'),
            'stand': (re.search(r'Lehrplan 21 · ([\d.]+)', text(d)) or
                      re.search(r'(23\.06\.2016)', text(d)) or
                      type('x', (), {'group': lambda s, n: ''})()).group(1),
            'url': quelle}


def lies_ueberfachlich(d):
    """Die codelosen überfachlichen Kompetenzen aus den ek_absatz-Blöcken lesen.

    Über die Auszeichnung, nicht über Satzgrenzen: eine Aufteilung nach
    Satzanfängen verliert zuverlässig die letzte Aussage jeder Gruppe, weil
    dort das nächste «können» fehlt.
    """
    gruppen, oberbegriff = {}, ''
    # Aufteilen statt Vorausschau: ein Abschlussanker lässt den letzten Block
    # verschwinden, sobald das Seitenende anders aussieht als erwartet.
    for roh in d.split('<div class="ek_absatz">')[1:]:
        titel = re.search(r'(?s)<div class="ek_titel">.*?<h2>(.*?)</h2>', roh)
        if titel:
            oberbegriff = text(titel.group(1))
            continue
        kopf = re.search(r'(?s)<div class="marginalie[^"]*">.*?<h4[^>]*>(.*?)</h4>', roh)
        if not kopf:
            continue
        teile = re.split(r'<br\s*/?>', kopf.group(1), 1)
        name = text(teile[0]).rstrip(':')
        untertitel = text(teile[1]) if len(teile) > 1 else ''
        koerper, _ = block(roh, 'ek_text')
        aussagen = [text(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', koerper or '', re.S)]
        aussagen = [a for a in aussagen if len(a) > 15]
        if not aussagen:
            continue
        perma = re.search(r'id="(101e200[A-Za-z0-9]+)"', roh)
        gruppen[name] = {'oberbegriff': oberbegriff, 'untertitel': untertitel,
                         'permalink': BASIS + '/' + perma.group(1) if perma else '',
                         'aussagen': aussagen}
    return gruppen


# ---------------------------------------------------------------- Index

def lade_index():
    if not os.path.exists(INDEX):
        return {}
    with open(INDEX, encoding='utf-8') as f:
        return json.load(f)


def befehl_index(args):
    """Alle Kompetenzcodes erfassen. Einmalig, danach arbeitet alles offline."""
    nur = [a.upper() for a in args if not a.startswith('-')]
    frisch = '--frisch' in args
    print('Übersichtsseiten sammeln …')
    # Nur die Startseite führt alle Fachbereiche. Von einem Fachbereich aus
    # kommt man nicht in die übrigen, das ergibt einen unvollständigen Index.
    # Die beiden Abrufe hier und beim Überfachlichen sind die einzigen ohne
    # eigenen Auffang — ohne sie ist der Lauf sinnlos, also bricht er sauber ab.
    try:
        start = hole('', frisch)
    except AbrufFehler as e:
        print(e)
        return 1
    ueber = sorted(set(re.findall(r'index\.php\?code=(b\|[\d|]+)', start)))
    if len(ueber) < 8:
        print('  Warnung: nur %d Fachbereichslinks auf der Startseite gefunden.' % len(ueber))
    for c in list(ueber):
        try:
            ueber += re.findall(r'index\.php\?code=(b\|[\d|]+)', hole(c, frisch))
        except Exception as e:
            print('  Fehler bei %s: %s' % (c, e))
    ueber = sorted(set(ueber))
    seiten = []
    for c in ueber:
        try:
            seiten += re.findall(r'index\.php\?code=(a\|[\d|]+)', hole(c, frisch))
        except Exception as e:
            print('  Fehler bei %s: %s' % (c, e))
    seiten = sorted(set(seiten))
    print('%d Übersichtsseiten, %d Kompetenzseiten' % (len(ueber), len(seiten)))

    # Ohne Kompetenzseiten gibt es nichts zu schreiben. Früher lief der Befehl
    # trotzdem durch, überschrieb index.json mit einem leeren Bestand und
    # meldete Erfolg — der schädlichste aller Ausgänge, weil er einen
    # brauchbaren Index gegen nichts eintauscht und das als gelungen ausgibt.
    if not seiten:
        print('Keine Kompetenzseiten gefunden. Der vorhandene Index bleibt '
              'unangetastet. Verbindung und Erreichbarkeit von %s prüfen.' % BASIS)
        return 1

    idx, fehler = lade_index(), 0
    for n, c in enumerate(seiten, 1):
        try:
            k = lies_kompetenz(hole(c, frisch), c)
        except Exception as e:
            fehler += 1
            print('  [%d/%d] %s nicht lesbar: %s' % (n, len(seiten), c, e))
            continue
        if nur and not any(k['code'].startswith(p + '.') for p in nur):
            continue
        idx[k['code']] = {'seite': c, 'permalink': k['permalink'], 'titel': k['titel'],
                          'pfad': k['pfad'], 'handlungsaspekt': k['handlungsaspekt'],
                          'stufen': [{'code': s['code'], 'zyklus': s['zyklus'],
                                      'text': s['text'], 'begriffe': s['begriffe']}
                                     for s in k['stufen']],
                          'vorangehend': k['vorangehend'], 'nachfolgend': k['nachfolgend']}
        if n % 25 == 0:
            print('  [%d/%d] …' % (n, len(seiten)))
    schreibe_json(INDEX, idx, ensure_ascii=False, indent=1, sort_keys=True)
    print('%d Kompetenzen im Index%s' % (len(idx), (', %d Fehler' % fehler) if fehler else ''))

    try:
        gr = lies_ueberfachlich(hole(UEFA_CODE, frisch))
    except AbrufFehler as e:
        print(e)
        print('  Der Kompetenzindex steht bereits; nur das Überfachliche fehlt.')
        return 1
    schreibe_json(UEFA, gr, ensure_ascii=False, indent=1)
    print('%d überfachliche Gruppen, %d Aussagen'
          % (len(gr), sum(len(v['aussagen']) for v in gr.values())))
    # Die Warnungen landeten früher nur in der Textausgabe, nie im
    # Rückgabewert: ein halb geratener Bestand meldete Erfolg. Über den
    # MCP-Server kam er beim Modell als isError:false an.
    unvollstaendig = 0
    if len(gr) != 9:
        print('  Warnung: der Lehrplan führt 9 überfachliche Gruppen, gelesen wurden %d.'
              % len(gr))
        unvollstaendig += 1
    if fehler:
        print('  Warnung: %d Kompetenzseiten waren nicht lesbar.' % fehler)
        unvollstaendig += 1
    # Ein Präfixlauf sammelt absichtlich weniger; dann ist die Zahl kein Mangel.
    if not nur and len(idx) < 350:
        print('  Warnung: %d Kompetenzen sind zu wenig, der Lehrplan führt rund 360.'
              % len(idx))
        unvollstaendig += 1
    return 1 if unvollstaendig else 0


# ---------------------------------------------------------------- Befehle

def hol_eintrag(code):
    idx = lade_index()
    code = code.upper()
    if code in idx:
        return code, idx[code]
    treffer = [c for c in idx if c.startswith(code)]
    if len(treffer) == 1:
        return treffer[0], idx[treffer[0]]
    if treffer:
        print('Mehrdeutig: ' + ', '.join(sorted(treffer)[:12]))
    else:
        print('%s steht nicht im Index. Zuerst «python lp21.py index» laufen lassen.' % code)
    return None, None


def befehl_zeige(args):
    # Fehlerpfade geben 1 zurück, nicht None. «return print(...)» liefert None
    # und damit Rückgabewert 0 — ein Fehlschlag sähe für jeden Aufrufer wie
    # Erfolg aus. Über den MCP-Server entscheidet genau dieser Wert darüber,
    # ob ein Modell die Antwort als gültig behandelt.
    if not args:
        print('Aufruf: lp21.py zeige NMG.11.3')
        return 1
    code, e = hol_eintrag(args[0])
    if not e:
        return 1
    print('=' * 72)
    print('%s   %s' % (code, e['titel']))
    print('=' * 72)
    if e['pfad']:
        print('Ort        : ' + ' › '.join(e['pfad']))
    if e['handlungsaspekt']:
        print('Aspekt     : ' + e['handlungsaspekt'])
    if e['vorangehend']:
        print('Vorangehend: ' + ', '.join(e['vorangehend']))
    if e['nachfolgend']:
        print('Nachfolgend: ' + ', '.join(e['nachfolgend']))
    print('Permalink  : ' + (e['permalink'] or '—'))
    if e['stufen']:
        print('\nKompetenzstufen')
        for s in e['stufen']:
            kopf = '  %-12s Zyklus %s' % (s['code'], s['zyklus'] or '?')
            for i, t in enumerate(s['text']):
                print(('%s  %s' % (kopf, t)) if i == 0 else (' ' * 24 + t))
            if s.get('begriffe'):
                print(' ' * 24 + 'verbindliche Inhalte: ' + ', '.join(s['begriffe']))


def befehl_zitat(args):
    if not args:
        print('Aufruf: lp21.py zitat ERG.5.6 [.a]')
        return 1
    ziel = args[0].upper()
    stufe = None
    m = re.match(r'^(.*?)\.([a-z])$', args[0])
    if m:
        ziel, stufe = m.group(1).upper(), m.group(2)
    code, e = hol_eintrag(ziel)
    if not e:
        return 1
    quelle = ('Bildungs- und Kulturdirektion des Kantons Bern, 2016. Lehrplan 21 für die '
              'Volksschule des Kantons Bern, Stand 23.06.2016.')
    print('In der Kompetenz %s «%s»' % (code, e['titel']))
    if stufe:
        tref = [s for s in e['stufen'] if s['code'].endswith('.' + stufe)]
        if not tref:
            print('Stufe %s gibt es bei %s nicht.' % (stufe, code))
            return 1
        print('lautet die Kompetenzstufe %s: «%s»' % (stufe, ' '.join(tref[0]['text'])))
    print('\nQuellenangabe')
    print('  ' + quelle)
    print('  ' + (e['permalink'] or BASIS + '/index.php?code=' + e['seite']))
    print('\nHinweis der Zitierhilfe: bei Kompetenzstufen die Kompetenz mitbenennen')
    print('oder den vollen Code angeben. Für formelle Papiere aus der Broschüre des')
    print('gesamten Fachbereichs mit Seitenzahl zitieren.')


def befehl_suche(args):
    if not args:
        print('Aufruf: lp21.py suche Konflikt')
        return 1
    n = ' '.join(args).lower()
    idx = lade_index()
    # Ohne diese Prüfung lief die Suche über ein leeres Wörterbuch, druckte
    # nichts und meldete Erfolg. Ein leerer Bildschirm liest sich dann als
    # «dazu steht nichts im Lehrplan 21» — eine stille falsche Verneinung,
    # und zwar in einem Werkzeug, dessen Zweck belastbare Belege sind.
    if not idx:
        print('Index fehlt. Zuerst «python lp21.py index» laufen lassen.')
        return 1
    treffer = 0
    for code in sorted(idx):
        e = idx[code]
        if n in e['titel'].lower():
            treffer += 1
            print('%-12s %s' % (code, e['titel']))
        for s in e['stufen']:
            for t in s['text']:
                if n in t.lower():
                    treffer += 1
                    print('%-12s   %s %s' % (code, s['code'], t[:110]))
    if os.path.exists(UEFA):
        with open(UEFA, encoding='utf-8') as f:
            for gruppe, e in json.load(f).items():
                for s in e['aussagen']:
                    if n in s.lower():
                        treffer += 1
                        print('%-12s %s' % ('überfachl.', '%s: %s' % (gruppe, s[:100])))
    # Keine Treffer ist ein gültiges Ergebnis, kein Fehler — aber es muss
    # ausgesprochen werden, damit es sich von der leeren Ausgabe unterscheidet.
    if not treffer:
        print('Keine Fundstelle zu «%s» im Bestand (%d Kompetenzen durchsucht).'
              % (' '.join(args), len(idx)))
    return 0


def befehl_baum(args):
    idx = lade_index()
    if not idx:
        print('Index fehlt. Zuerst «python lp21.py index» laufen lassen.')
        return 1
    praefix = args[0].upper() if args else ''
    ebenen = {}
    for code in sorted(idx, key=lambda c: [int(x) if x.isdigit() else x
                                           for x in re.split(r'[.]', c)]):
        if praefix and not code.startswith(praefix):
            continue
        e = idx[code]
        pfad = e['pfad'] or ['?']
        # Der Lehrplan ist je nach Fachbereich zwei- oder dreistufig.
        ort = ' › '.join(pfad[:-1]) if len(pfad) > 1 else pfad[0]
        bereich = pfad[-1] if len(pfad) > 1 else ''
        ebenen.setdefault(ort, {}).setdefault(bereich, []).append((code, e['titel']))
    if not ebenen:
        print('Kein Eintrag mit Präfix «%s» im Bestand (%d Kompetenzen).'
              % (praefix, len(idx)))
        return 1
    for ort in sorted(ebenen):
        print('\n' + ort)
        for bereich in ebenen[ort]:
            print('  ' + (bereich or '—'))
            for code, titel in ebenen[ort][bereich]:
                print('    %-12s %s' % (code, titel[:88]))
    return 0


def kuerze(s, n=96):
    """Lange Zitate mittig kürzen, damit Anfang und Ende sichtbar bleiben."""
    if len(s) <= n:
        return s
    return s[:n - 34] + ' … ' + s[-30:]


def markdown_aufzaehlung(inhalt):
    """Aufzählungspunkte, die wie ein Kompetenzwortlaut beginnen, mitprüfen.

    In der Zuordnungsdatei stehen die überfachlichen Kompetenzen als Liste
    ohne Guillemets. Ohne diesen Griff bleibt genau der Teil ungeprüft, in
    dem sich am ehesten ein falsches Verb einnistet.
    """
    treffer, sammler = [], None
    for zeile in inhalt.splitlines() + ['']:
        anfang = re.match(r'^\s*[-*]\s+(.*)$', zeile)
        if anfang:
            if sammler:
                treffer.append(sammler)
            sammler = anfang.group(1)
        elif sammler is not None and zeile.startswith((' ', '\t')) and zeile.strip():
            sammler += ' ' + zeile.strip()
        else:
            if sammler:
                treffer.append(sammler)
            sammler = None
    sauber = []
    for t in treffer:
        t = re.split(r'\s*←', t)[0]
        t = re.sub(r'\*\*|__', '', t).strip()
        if re.match(r'^(können|kennen|lernen|verstehen|nehmen|reflektieren)\b', t) and len(t) > 25:
            sauber.append(t)
    return sauber


def docx_text(pfad):
    with zipfile.ZipFile(pfad) as z:
        d = z.read('word/document.xml').decode('utf-8', 'replace')
    d = re.sub(r'</w:p>', '\n', d)
    return html.unescape(re.sub(r'<[^>]+>', '', d))


def befehl_pruefe(args):
    """Codes und «…»-Zitate aus einer Datei gegen den Index prüfen."""
    if not args:
        print('Aufruf: lp21.py pruefe datei.docx | datei.md')
        return 1
    pfad = args[0]
    if not os.path.exists(pfad):
        print('Datei nicht gefunden: ' + pfad)
        return 1
    # Zwei alltägliche Fehlbedienungen warfen hier rohe Tracebacks: eine unter
    # Windows angelegte Textdatei in cp1252 und eine Datei, die nur .docx heisst.
    try:
        if pfad.lower().endswith('.docx'):
            inhalt = docx_text(pfad)
        else:
            with open(pfad, encoding='utf-8', errors='replace') as f:
                inhalt = f.read()
    except zipfile.BadZipFile:
        print('%s ist keine .docx-Datei. Word-Dateien sind Zip-Archive; diese '
              'hier ist keines — vermutlich umbenannt statt umgewandelt.'
              % os.path.basename(pfad))
        return 1
    except OSError as e:
        print('Datei nicht lesbar: %s' % e)
        return 1

    idx = lade_index()
    if not idx:
        print('Index fehlt. Zuerst «python lp21.py index» laufen lassen.')
        return 1
    uefa = json.load(open(UEFA, encoding='utf-8')) if os.path.exists(UEFA) else {}

    print('Datei: %s\n' % os.path.basename(pfad))
    codes = sorted(set(re.findall(r'\b([A-Z]{1,4}\.\d+(?:\.[A-Z])?\.\d+)\b', inhalt)))
    print('— Codes (%d) —' % len(codes))
    unbekannt = 0
    for c in codes:
        if c in idx:
            print('  ok       %-12s %s' % (c, idx[c]['titel'][:78]))
        else:
            unbekannt += 1
            print('  UNBEKANNT %-12s steht nicht im Lehrplan' % c)

    stufen = sorted(set(re.findall(r'\b([A-Z]{1,4}\.\d+(?:\.[A-Z])?\.\d+\.[a-z])\b', inhalt)))
    if stufen:
        print('\n— Kompetenzstufen (%d) —' % len(stufen))
        alle = {s['code'] for e in idx.values() for s in e['stufen']}
        for s in stufen:
            print('  %-9s %s' % ('ok' if s in alle else 'UNBEKANNT', s))

    quellen = [t for e in idx.values() for s in e['stufen'] for t in s['text']]
    quellen += [e['titel'] for e in idx.values()]
    quellen += [s for v in uefa.values() for s in v['aussagen']]
    # Gruppenname und Untertitel der überfachlichen Kompetenzen gehören dazu.
    # Sie tragen keinen Code, also ist ihr Wortlaut der Verweis, und wer sie
    # zitiert, soll es geprüft tun können.
    quellen += list(uefa)
    quellen += [v['untertitel'] for v in uefa.values()]
    # Kompetenzbereiche und Handlungsaspekte werden ebenfalls zitiert, also
    # die Zwischenüberschriften des Lehrplans, nicht nur die Kompetenzen selbst.
    # Bewusst ohne Beispiel aus dem Lehrplan: dieses Repositorium gibt keinen
    # Lehrplantext weiter, auch nicht satzweise in einem Kommentar.
    for e in idx.values():
        quellen += [re.sub(r'^\d+\s+', '', p) for p in e['pfad']]
        if e['handlungsaspekt']:
            quellen.append(e['handlungsaspekt'])
    quellen = [q for q in quellen if q]
    heu = '\n'.join(quellen)

    zitate = re.findall(r'«([^»]{12,})»', inhalt)
    zitate += markdown_aufzaehlung(inhalt)
    print('\n— Wörtliche Zitate (%d) —' % len(zitate))
    offen, fremd, gekappt = 0, 0, 0
    for z in zitate:
        k = ' '.join(z.split()).rstrip('.').strip()
        # Markdown-Hervorhebung gehört dem zitierenden Text, nicht der Quelle.
        k = re.sub(r'\*\*|__|(?<!\w)[*_](?=\w)|(?<=\w)[*_](?!\w)', '', k)
        k = ' '.join(k.split())
        # Markierte Auslassung: nur bis dorthin vergleichen, der Rest fehlt
        # absichtlich und ist als Kürzung gekennzeichnet.
        gekuerzt = re.split(r'\s*(?:\[…\]|\[\.\.\.\]|…)\s*', k)[0].strip()
        if k in heu:
            # Teiltreffer sind zulässig, eine unmarkierte Kürzung des
            # Satzendes ist aber genau die Abweichung, die beim Lesen nicht
            # auffällt. Deshalb sichtbar machen, ohne sie als Fehler zu werten.
            rest = ''
            for q in quellen:
                if q.startswith(k) and len(q.rstrip('.')) > len(k) + 15:
                    rest = q.rstrip('.')[len(k):].strip()
                    break
            if rest:
                gekappt += 1
                print('  gekürzt  «%s»' % kuerze(k))
                print('           die Quelle führt weiter: «%s»' % kuerze(rest, 70))
            else:
                print('  ok       «%s»' % kuerze(k))
            continue
        if gekuerzt != k and len(gekuerzt) > 15 and gekuerzt in heu:
            print('  ok       «%s»  (markierte Kürzung)' % kuerze(gekuerzt))
            continue
        beste, gemein = None, 0
        for q in quellen:
            n = len(os.path.commonprefix([k, q]))
            if n > gemein:
                beste, gemein = q, n
        if beste is None or gemein < 20:
            # Kein Lehrplanwortlaut, etwa eine eigene Themenüberschrift.
            # Das ist kein Zitierfehler und darf den Lauf nicht scheitern lassen.
            fremd += 1
            print('  extern   «%s»  kein Lehrplanbezug erkennbar' % kuerze(k, 60))
            continue
        offen += 1
        print('  PRUEFEN  «%s»' % kuerze(k))
        # Auf die Wortgrenze zurücksetzen, sonst bricht die Anzeige mitten im
        # Wort um und «anwenden» gegen «akzeptieren» liest sich als «nwenden».
        schnitt = k.rfind(' ', 0, gemein + 1)
        schnitt = schnitt + 1 if schnitt > 0 else gemein
        print('           Quelle   «%s»' % kuerze(beste))
        print('           ab Zeichen %d: «%s» statt «%s»'
              % (schnitt, k[schnitt:][:46] or '(nichts)', beste[schnitt:][:46] or '(nichts)'))

    print('\n%d Codes, %d unbekannt · %d Zitate, %d zu prüfen, %d gekürzt, '
          '%d ohne Lehrplanbezug'
          % (len(codes), unbekannt, len(zitate), offen, gekappt, fremd))
    return 1 if (unbekannt or offen) else 0


def befehl_ueberfachlich(args):
    if not os.path.exists(UEFA):
        print('Noch nicht erfasst. Zuerst «python lp21.py index».')
        return 1
    with open(UEFA, encoding='utf-8') as f:
        gr = json.load(f)
    n = ' '.join(args).lower()
    for gruppe, e in gr.items():
        if n and n not in gruppe.lower() and not any(n in s.lower() for s in e['aussagen']):
            continue
        print('\n%s — %s' % (gruppe, e['untertitel']))
        print('  %s · %s' % (e['oberbegriff'], e['permalink'] or '—'))
        for s in e['aussagen']:
            print('  · ' + s)
    print('\nDiese Kompetenzen tragen im Lehrplan 21 keine Codes.')
    print('Sie werden über Gruppe und Wortlaut zitiert.')


def fachbereich(pfad):
    """Den Fachbereich aus dem Pfad ziehen.

    Sprachen, Gestalten und Natur, Mensch, Gesellschaft bündeln mehrere
    Fachbereiche unter sich, dort trägt die zweite Pfadstufe den Fachbereich.
    Ist sie nummeriert, ist sie bereits ein Kompetenzbereich, und die erste
    Stufe ist der Fachbereich. Das ergibt die sechzehn Fachbereiche und Module.
    """
    if len(pfad) > 1 and pfad[1] and not pfad[1][0].isdigit():
        return pfad[1]
    return pfad[0] if pfad else 'Ohne Zuordnung'


def dateiname(name):
    """Name ohne Umlaute und Sonderzeichen, damit er auf jedem der beteiligten
    Rechner gleich heisst und jede Dateiablage unbeschadet übersteht."""
    s = name.lower()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        s = s.replace(a, b)
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-') or 'ohne-zuordnung'


def nach_code(code):
    """Sortierschlüssel, der Zahlen numerisch nimmt, ohne Zahl gegen Buchstabe
    zu vergleichen. NMG.10.1 gehört hinter NMG.9.1, nicht dazwischen."""
    return [(0, int(x), '') if x.isdigit() else (1, 0, x) for x in code.split('.')]


def abschnitt(code, e):
    """Eine Kompetenz als Markdown-Abschnitt, Wortlaut vor Verwaltungsangaben."""
    zeilen = ['## %s · %s' % (code, e['titel']), '']
    if e['pfad']:
        zeilen.append('Ort im Lehrplan: ' + ' / '.join(e['pfad']))
    if e['handlungsaspekt']:
        zeilen.append('Handlungsaspekt: ' + e['handlungsaspekt'])
    if e['vorangehend']:
        zeilen.append('Vorangehende Kompetenzen: ' + ', '.join(e['vorangehend']))
    if e['nachfolgend']:
        zeilen.append('Nachfolgende Kompetenzen: ' + ', '.join(e['nachfolgend']))
    if e['permalink']:
        zeilen.append('Permalink: ' + e['permalink'])
    zeilen.append('')
    for s in e['stufen']:
        zeilen.append('### %s (Zyklus %s)' % (s['code'], s['zyklus'] or '?'))
        for t in s['text']:
            zeilen.append('- ' + t)
        if s.get('begriffe'):
            zeilen.append('- Verbindliche Inhalte: ' + '; '.join(s['begriffe']))
        zeilen.append('')
    return '\n'.join(zeilen)


def befehl_export(args):
    """Den Bestand als Markdown ausgeben, eine Datei je Fachbereich.

    Gedacht für Werkzeuge, die Fliesstext lesen und daraus einen Graphen bauen.
    Eine einzelne JSON-Datei sehen sie als einen einzigen Knoten, ein Abschnitt
    je Kompetenz gibt ihnen Wortlaut, Ort und Verweise einzeln.

    Der Lehrplan zieht deklarierte Verweise nur dort, wo ein Fachbereich beim
    Zyklenwechsel den Namen wechselt, also im NMG-Verbund. 224 der 363
    Kompetenzen stehen ohne jede Kante, darunter Bewegung und Sport sowie
    Medien und Informatik vollständig. Was dort inhaltlich zusammengehört,
    steht im Wortlaut und nirgends sonst.

    Die Ausgabe ist abgeleitet und jederzeit neu herstellbar. Sie liegt trotzdem
    im Skriptordner und damit im Abgleich, weil sie dort gebraucht wird, wo der
    Graph gebaut wird. Rund 630 kB neben den 910 kB, die der Ordner ohnehin hat.
    """
    idx = lade_index()
    if not idx:
        print('Index fehlt. Zuerst «python lp21.py index» laufen lassen.')
        return 1
    ziel = args[0] if args else os.path.join(HIER, 'bestand')
    os.makedirs(ziel, exist_ok=True)
    quelle = ('Bildungs- und Kulturdirektion des Kantons Bern, 2016. Lehrplan 21 für die '
              'Volksschule des Kantons Bern, Stand 23.06.2016.')

    faecher = {}
    for code, e in idx.items():
        faecher.setdefault(fachbereich(e['pfad']), {})[code] = e

    gesamt = 0
    for fach in sorted(faecher):
        codes = faecher[fach]
        teile = ['# %s' % fach, '',
                 '%d Kompetenzen des Fachbereichs %s.' % (len(codes), fach),
                 'Quelle: %s' % quelle, '']
        for code in sorted(codes, key=nach_code):
            teile.append(abschnitt(code, codes[code]))
        datei = os.path.join(ziel, dateiname(fach) + '.md')
        with open(datei, 'w', encoding='utf-8') as f:
            f.write('\n'.join(teile))
        gesamt += os.path.getsize(datei)
        print('  %-52s %3d Kompetenzen' % (os.path.basename(datei), len(codes)))

    if os.path.exists(UEFA):
        with open(UEFA, encoding='utf-8') as f:
            gr = json.load(f)
        teile = ['# Überfachliche Kompetenzen', '',
                 'Diese Kompetenzen tragen im Lehrplan 21 keine Codes, zitiert wird über',
                 'Gruppe und Wortlaut.',
                 'Quelle: %s' % quelle, '']
        for gruppe, e in gr.items():
            teile += ['## %s' % gruppe, '',
                      'Oberbegriff: ' + e['oberbegriff'],
                      'Untertitel: ' + e['untertitel'],
                      'Permalink: ' + (e['permalink'] or '—'), '']
            teile += ['- ' + s for s in e['aussagen']]
            teile.append('')
        datei = os.path.join(ziel, 'ueberfachliche-kompetenzen.md')
        with open(datei, 'w', encoding='utf-8') as f:
            f.write('\n'.join(teile))
        gesamt += os.path.getsize(datei)
        print('  %-52s %3d Aussagen'
              % (os.path.basename(datei), sum(len(v['aussagen']) for v in gr.values())))

    print('\n%d Fachbereiche, %d Kompetenzen, %.0f kB nach %s'
          % (len(faecher), len(idx), gesamt / 1024.0, ziel))
    return 0


def befehl_status(args):
    """Zeigt, ob auf diesem Rechner alles Nötige vorhanden ist."""
    import platform
    print('Rechner    : %s, Python %s' % (platform.node(), platform.python_version()))
    print('Skriptort  : %s' % HIER)
    print('Zwischensp.: %s%s' % (CACHE, '' if os.path.isdir(CACHE) else '  (noch nicht angelegt)'))
    fehlt = 0
    for name, pfad in (('Index', INDEX), ('Überfachlich', UEFA)):
        if os.path.exists(pfad):
            groesse = os.path.getsize(pfad) / 1024.0
            zeit = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(pfad)))
            print('%-11s: %.0f kB, Stand %s' % (name, groesse, zeit))
        else:
            fehlt += 1
            print('%-11s: FEHLT' % name)
    if fehlt:
        print('\nOhne diese Dateien läuft nur «index». Einmal «python lp21.py index»')
        print('starten, dann arbeiten alle übrigen Befehle ohne Netz.')
        return 1
    idx = lade_index()
    with open(UEFA, encoding='utf-8') as f:
        gr = json.load(f)
    stufen = sum(len(e['stufen']) for e in idx.values())
    print('Bestand    : %d Kompetenzen, %d Kompetenzstufen, %d überfachliche Gruppen'
          % (len(idx), stufen, len(gr)))
    if len(idx) < 350 or len(gr) != 9:
        print('  Warnung: der Bestand wirkt unvollständig, erwartet sind rund 360')
        print('  Kompetenzen und 9 Gruppen. Ein Lauf «index --frisch» baut ihn neu auf.')
        return 1
    # hol_eintrag gibt (None, None) zurück, wenn der Code fehlt. Ohne diese
    # Prüfung endete ein Bestand ohne ERG.5.6 in einem rohen TypeError —
    # ausgerechnet im Befehl, der melden soll, dass etwas nicht stimmt.
    probe, e = hol_eintrag('ERG.5.6')
    if not e:
        print('Stichprobe : ERG.5.6 fehlt im Bestand, obwohl die Zahlen stimmen.')
        print('  Ein Lauf «index --frisch» baut ihn neu auf.')
        return 1
    print('Stichprobe : %s trägt %d Stufen und %d vorangehende Kompetenzen'
          % (probe, len(e['stufen']), len(e['vorangehend'])))
    print('\nAlles vorhanden. Die Lesebefehle arbeiten ohne Netz.')
    return 0


HILFE = """Zitier- und Navigierhilfe für den Lehrplan 21, Kantonsfassung Bern.

  status                         prüfen, ob auf diesem Rechner alles da ist
  index [PRAEFIX...] [--frisch]  alle Kompetenzen erfassen, einmalig nötig
  zeige CODE                     Wortlaut, Stufen, Verweise, Permalink
  zitat CODE[.stufe]             Quellenangabe nach der Zitierhilfe
  suche TEXT                     Volltext über Titel, Stufen, Überfachliches
  baum [PRAEFIX]                 Navigation nach Fachbereich und Kompetenzbereich
  pruefe DATEI                   Codes und «…»-Zitate einer .docx/.md prüfen
  ueberfachlich [TEXT]           die codelosen überfachlichen Kompetenzen
  export [ORDNER]                Bestand als Markdown, eine Datei je Fachbereich

Beispiele
  python lp21.py index
  python lp21.py zeige ERG.5.6
  python lp21.py zitat ERG.5.6.d
  python lp21.py suche Konflikt
  python lp21.py pruefe unterrichtsplanung.docx
  python lp21.py export
"""


def main():
    befehle = {'index': befehl_index, 'zeige': befehl_zeige, 'zitat': befehl_zitat,
               'suche': befehl_suche, 'baum': befehl_baum, 'pruefe': befehl_pruefe,
               'ueberfachlich': befehl_ueberfachlich, 'status': befehl_status,
               'export': befehl_export}
    if len(sys.argv) < 2 or sys.argv[1] in ('hilfe', '-h', '--help'):
        print(HILFE)
        return 0
    f = befehle.get(sys.argv[1])
    if not f:
        # Ausgabe nach stderr und Rückgabewert 1: ein Tippfehler im Befehl darf
        # in einem Skript nicht als gelungener Lauf durchgehen.
        sys.stderr.write('Unbekannter Befehl «%s».\n\n%s\n' % (sys.argv[1], HILFE))
        return 1
    rc = f(sys.argv[2:])
    return rc if isinstance(rc, int) else 0


if __name__ == '__main__':
    # main() gibt den Rückgabewert zurück, statt selbst auszusteigen — sonst
    # verpuffen die Fehlerwerte der Zweige davor, die kein sys.exit erreichen.
    sys.exit(main())
