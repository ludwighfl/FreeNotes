# FreeNotes – Neue Aufgabenliste

Geordnet nach Themengebiet, Abhängigkeiten und Implementierungsreihenfolge.
Punkte innerhalb einer Phase sollten in der angegebenen Reihenfolge umgesetzt
werden, da spätere Punkte häufig auf früheren aufbauen.

---

## Phase 1 – Kritische Bugfixes (Blockierend)

### 1.1 PDF-Export: Crash mit `'DocumentManager' object has no attribute 'load'`
**Problem:** Der ZIP-Export (`ZipExporter.export_annotated_pdfs`) baut intern
eine temporäre `PageScene` mit `DocumentManager` auf. Dieser wird über
`dm.load(str(pdf_path))` initialisiert – die Methode heißt jedoch
`open_document`, nicht `load`. Der Export aller PDFs schlägt daher
ausnahmslos fehl.  
**Fix:** In `core/zip_exporter.py` → `_build_temp_scene` den Aufruf
`dm.load(...)` durch `dm.open_document(...)` ersetzen. Denselben Aufruf auch
in `ui/windows/manager_action_bar_mixin.py` → `_on_action_export` prüfen,
wo ebenfalls ein temporärer `DocumentManager` instantiiert wird.  
**Betroffene Dateien:** `core/zip_exporter.py`,
`ui/windows/manager_action_bar_mixin.py`

### 1.2 PDF-Export: Z-Ebenen-Reihenfolge wird nicht beachtet
**Problem:** `PdfExporter.export` rendert Annotationstypen in einer festen
Reihenfolge unabhängig von den Z-Werten der Items in der Scene. Dadurch
erscheinen z. B. Highlights über handschriftlichen Strichen statt darunter.  
**Fix:** Die korrekte Render-Reihenfolge entspricht den Z-Werten der Scene:
Images (Z=2) → Highlights (Z=5) → Strokes (Z=10) → Shapes/TextBoxen (Z=10/15).
Da PyMuPDF auf einer Seite sequenziell malt (spätere Elemente liegen oben),
reicht eine Umsortierung der `export_*`-Aufrufe in `PdfExporter.export`.  
**Betroffene Dateien:** `core/pdf_exporter.py`

### 1.3 Präzisionsradierer: Artefakte und doppelte Linien nach Speichern/Laden
**Problem:** Strokes die mit dem Präzisionsradierer bearbeitet wurden, werden
beim Speichern im Outline-Mode (`_outline_mode=True`, gefüllter Pfad)
gespeichert. Beim Laden werden sie als normale Strokes (dünne Linie)
deserialisiert, was zu doppelten Linien und visuellen Artefakten führt.  
**Fix:** `FreenotesStore._serialize_stroke` muss das `_outline_mode`-Flag und
den zugehörigen gefüllten Pfad korrekt serialisieren. `_deserialize_stroke`
muss `_outline_mode` beim Laden wiederherstellen, sodass das Item nach dem
Laden visuell identisch zum Zustand vor dem Speichern ist.  
**Betroffene Dateien:** `core/freenotes_store.py`, `items/stroke_item.py`

### 1.4 Präzisionsradierer: Kein Undo für Shape- und Image-Annotationen
**Problem:** `EraserTool._erase_pixel_mode` behandelt `ShapeItem` und
`ImageItem` bereits als Sonderfall (ganzes Item löschen statt Pfad subtrahieren),
erzeugt dabei aber einen `_affected_items`-Eintrag mit `None` als Pfad.
`ModifyStrokeCommand` deckt diesen Fall nicht ab, weshalb Undo nicht
funktioniert.  
**Fix:** In `ViewerToolManagerMixin._on_action_completed` für den Pixel-Eraser
sicherstellen, dass vollständig gelöschte Shapes/Images als `DeleteItemsCommand`
gepusht werden – analog zum Objektradierer. Der `ModifyStrokeCommand` bleibt
ausschließlich für tatsächliche Pfad-Modifikationen an `StrokeItem` und
`HighlightItem` zuständig.  
**Betroffene Dateien:** `tools/eraser_tool.py`,
`ui/windows/viewer_tool_manager.py`

### 1.5 Pfeilspitzen zeigen nach Export in falsche Richtung
**Problem:** `PdfShapeExporter._draw_arrow_shape` berechnet die Pfeilrichtung
immer aus `rect.x0/y0` → `rect.x1/y1` (TL→BR). Das `_line_dir`-Flag des
`ShapeItem`, das die tatsächliche Richtung des Pfeils bestimmt, wird nicht
berücksichtigt.  
**Fix:** In `PdfShapeExporter._export_single_shape` das `_line_dir`-Attribut
des `ShapeItem` auslesen und `p1`/`p2` entsprechend tauschen, bevor
`_draw_arrow_shape` aufgerufen wird – analog zur `_get_line_points`-Logik in
`ShapeItem.paint`.  
**Betroffene Dateien:** `core/pdf_shape_exporter.py`

### 1.6 Rotierte Image-Annotationen werden nicht exportiert
**Problem:** `PdfImageExporter._export_single_image` übergibt den
`rotation`-Wert direkt an `fitz.Page.insert_image(rotate=...)`. PyMuPDF
akzeptiert dort nur Vielfache von 90°. Jede andere Rotation wirft
`bad rotate value` und die gesamte Image-Annotation fehlt im Export.  
**Fix:** Für beliebige Rotationswinkel die Bitmap vor dem Export clientseitig
drehen: `QPixmap.transformed(QTransform().rotate(angle))` anwenden und das
gedrehte Bild als PNG-Bytes an `insert_image` übergeben (mit `rotate=0`).  
**Betroffene Dateien:** `core/pdf_image_exporter.py`

---

## Phase 2 – Interaktions-Bugfixes (Viewer)

Korrekturen an bestehendem Interaktionsverhalten, die keine neuen Features
erfordern, aber die tägliche Nutzung direkt beeinträchtigen.

### 2.1 Selektion: Maximal eine aktive Selektion gleichzeitig
**Problem:** Beim Erstellen neuer TextBoxen oder beim Wechseln zwischen
Annotationen können mehrere Selections gleichzeitig aktiv sein, was zu
inkonsistenten Handle-Zuständen und visuellen Fehlern führt.  
**Fix:** Vor jeder neuen Selektion (insbesondere in `TextTool.on_press` beim
Erstellen einer neuen TextBox und in `ShapeTool.on_release`) `scene.clear_selection()`
aufrufen, um bestehende Selections vollständig aufzuheben. Sicherstellen, dass
`PageScene.set_selection` intern immer zuerst deselektiert.  
**Betroffene Dateien:** `tools/text_tool.py`, `tools/shape_tool.py`,
`ui/scene/scene_selection.py`

### 2.2 Selections außerhalb der PDF-Seite bugen
**Problem:** Wenn Annotationen über den PDF-Rand hinausgehen oder auf dem
Hintergrund/Border außerhalb der Seitenrechtecke selektiert werden, entstehen
fehlerhafte visuelle Darstellungen (Handles an falschen Positionen,
Selection-Overlays die aus dem Seitenbereich herausragen).  
**Fix:** Annotation-Items beim Platzieren auf die Grenzen der zugehörigen
PDF-Seite (`_page_rects[page_index]`) clampen, oder zumindest die
Handle-Positionierung so absichern, dass sie bei Positionen außerhalb des
sichtbaren Bereichs korrekt berechnet werden. Für die Selection-Overlay-Darstellung
eine Clip-Region setzen.  
**Betroffene Dateien:** `ui/scene/scene_selection.py`,
`items/selection_overlay_item.py`, `items/bounding_box_handle_manager.py`

### 2.3 TextBoxen: Kopieren/Ausschneiden über Kontextmenü wie bei Shapes
**Problem:** `ShapeItem` hat über `ShapeOptionsHandle` und `tool_context_menu.py`
vollständige Kopieren/Ausschneiden-Funktionalität. `TextBoxItem` verwendet
hingegen noch das ältere `TextBoxOptionsPopup` (separates Floating-Widget),
das inkonsistent mit dem Rest der Annotation-Interaktion ist.  
**Fix:** `TextBoxItem` auf dasselbe Kontextmenü-System wie Shapes umstellen.
Das bestehende `TextBoxOptionsPopup` kann entfernt werden. Kopieren/Ausschneiden
von TextBox-Objekten (als Annotations-Objekte, nicht als Text-Inhalt) über
`scene.copy_selected()` / `scene.cut_selected()` routen.  
**Betroffene Dateien:** `items/text_box_item.py`,
`ui/popups/textbox_options_popup.py`,
`ui/windows/viewer_tool_manager.py`

---

## Phase 3 – Neue Interaktionsfunktionen (Viewer)

Erweiterungen am bestehenden Interaktionsmodell. Setzt Phase 2 voraus, da
korrekte Selektions-Grundlagen benötigt werden.

### 3.1 Style-Änderung (Farbe/Breite) auf markierten Annotationen
**Problem/Verhalten:** Wenn Strokes, Textmarker oder Shapes selektiert sind und
der Nutzer in der Toolbar eine andere Farbe oder Breite wählt, sollen die
selektierten Items sofort aktualisiert werden.  
**Details:**
- Für `StrokeItem`: `_style.color` und `_style.width` updaten,
  `prepareGeometryChange()` + `update()` aufrufen. Über neues
  `ChangeStrokeStyleCommand` mit Undo-Support.
- Für `HighlightItem`: analog, nur `_style.color` relevant (Breite ist fix).
- Für `ShapeItem`: bereits über `ChangeShapeStyleCommand` implementiert –
  sicherstellen, dass dies auch bei Mehrfachauswahl greift.
- Farbwechsel bei TextBox als Objekt (nicht als Textinhalt) ist nicht
  vorgesehen – TextBox-Farbe wird weiterhin über die FormattingBar gesteuert.  
**Betroffene Dateien:** `ui/windows/viewer_tool_manager.py`,
`items/stroke_item.py`, `items/highlight_item.py`,
neues `commands/change_stroke_style_command.py`

### 3.2 Textmarker: Vertikale Skalierung bei Selektion
**Problem:** `HighlightItem` ist konzeptionell eine horizontale Linie mit
fester Y-Position. Aktuell sind beim Resize via `BoundingBoxHandleManager`
nur horizontale Handles (links/rechts) sinnvoll nutzbar; vertikale Handles
verändern zwar `boundingRect`, aber nicht die visuelle Breite des Markers.  
**Fix:** Beim Resize eines `HighlightItem` über die oberen/unteren Handles soll
die `_style.width` (= Strichdicke des Markers) proportional zur neuen Höhe
angepasst werden. Das ermöglicht effektiv eine vertikale Skalierung.
`ResizeHighlightCommand` muss den alten/neuen `width`-Wert zusätzlich
speichern.  
**Betroffene Dateien:** `items/highlight_item.py`,
`items/bounding_box_handle_manager.py`,
`commands/resize_highlight_command.py`

### 3.3 Shift + Rotate-Handle: Einrasten in 45°-Schritten
**Verhalten:** Wenn der Nutzer beim Drehen einer Annotation (TextBox, Shape,
Image) die Shift-Taste hält, soll die Rotation in 45°-Schritten einrasten
(0°, 45°, 90°, 135°, 180°, …).  
**Technische Umsetzung:** In `RotateHandleItem.mouseMoveEvent` sowie in
`ShapeRotateHandle.mouseMoveEvent` den berechneten Winkel bei gehaltener
Shift-Taste auf das nächste Vielfache von 45° runden:
`snapped = round(angle / 45) * 45`.  
**Betroffene Dateien:** `items/rotate_handle_item.py`,
`items/shape_handles.py`

### 3.4 Shift + Line/Arrow-Handle: Einrasten in 45°-Schritten
**Verhalten:** Beim Ziehen der Endpunkt-Handles von Line- und Arrow-Shapes
soll Shift die Richtung auf 45°-Schritte einrasten lassen (0°, 45°, 90°,
135°, …).  
**Technische Umsetzung:** In `ShapeResizeHandle.mouseMoveEvent` (für Handles
vom Typ `TOP_LEFT` / `BOT_RIGHT` bei linearen Shapes) bei gehaltener Shift-Taste
das Bewegungs-Delta auf den nächsten 45°-Winkel snappen – analog zur
`_build_rect`-Logik in `ShapeTool.on_move`.  
**Betroffene Dateien:** `items/shape_handles.py`, `items/shape_item.py`

### 3.5 Shift beim Skalieren: Proportionale Größenänderung (Shapes und Images)
**Verhalten:** Beim Ziehen eines Ecken-Handles (TL, TR, BL, BR) an einem
`ShapeItem` (Rechteck, Ellipse, abgerundetes Rechteck, Dreieck) oder einem
`ImageItem` soll das Halten von Shift das Seitenverhältnis beibehalten.  
**Technische Umsetzung:** In `apply_handle_drag` beider Item-Typen bei
Shift-Modifier das Delta so korrigieren, dass `new_width / new_height ==
original_width / original_height` gilt. Der `start_rect` aus dem Handle liefert
das Original-Verhältnis. Nur für Ecken-Handles relevant; Kanten-Handles (ML,
MR) bleiben unverändert.  
**Hinweis:** Für Line/Arrow-Shapes ist diese Funktion nicht sinnvoll (→ 3.4).  
**Betroffene Dateien:** `items/shape_item.py`, `items/image_item.py`,
`items/handle_item.py`

### 3.6 Rotation bei Mehrfachauswahl
**Problem:** Beim Selection-Tool mit mehreren selektierten Items fehlt ein
gemeinsamer Rotate-Handle. Das `SelectionOverlayItem` bietet zwar
Resize-Handles über den `BoundingBoxHandleManager`, aber keinen Rotations-Handle.  
**Verhalten:** Ein einzelner Rotate-Handle unterhalb des gemeinsamen
Bounding-Box-Overlays soll alle selektierten Items gleichzeitig um den
gemeinsamen Mittelpunkt rotieren. Jedes Item erhält dabei seine eigene
Rotations-Änderung (Delta-Rotation), sodass individuelle Vorrotationen
erhalten bleiben. Undo/Redo: Ein kombiniertes Command speichert die
Rotation aller betroffenen Items.  
**Hinweis:** Funktioniert auch für Mehrfachauswahl aus gemischten Typen
(Strokes, Shapes, TextBoxen, Images).  
**Betroffene Dateien:** `items/selection_overlay_item.py`,
`items/bounding_box_handle_manager.py`,
neues `commands/rotate_items_command.py`

---

## Phase 4 – Performance-Optimierung

### [x] 4.1 Ladeverhalten bei sehr großen PDFs (400+ Seiten, 200+ MB)
**Problem:** Beim Öffnen sehr großer, unoptimierter PDFs (z. B. lange
Slide-Präsentationen mit eingebetteten Hochauflösungs-Bildern) kommt es zu
spürbaren Wartezeiten beim initialen Laden, obwohl das Tile-Rendering selbst
einwandfrei funktioniert.  
**Ursache:** `DocumentManager.open_document` öffnet das Dokument synchron im
Haupt-Thread. Bei sehr großen Dateien dauert `fitz.open(path)` selbst mehrere
Sekunden, was den UI-Thread blockiert.  
**Fix (Workaround ohne Änderung am Rendering):**
- `fitz.open` in einen `QThread` / `StartupWorker`-ähnlichen Hintergrund-Thread
  auslagern. Während des Ladens zeigt der Viewer einen Lade-Indikator
  (Spinner oder Fortschrittsbalken im Header).
- Die `PageScene.load_document`-Initialisierung (Placeholder-Layout) kann
  sofort nach Kenntnis der Seitenanzahl erfolgen – diese ist über
  `fitz.open(..., filetype="pdf")` mit `doc.page_count` ohne vollständiges
  Parsen aller Seiten abrufbar.
- Die `PdfConnectionPool` im `TileRenderer` öffnet bereits eigene
  fitz-Instanzen pro Thread; der Haupt-Thread braucht nur eine einzige
  offene Instanz für Metadaten und Seitengrößen.  
**Betroffene Dateien:** `core/document_manager.py`,
`ui/windows/viewer_file_io.py`, `ui/windows/viewer_window.py`

---

## Phase 5 – ManagerView Erweiterungen

### [x] 5.1 Neue Funktion „Neue Notiz" unter „Erstellen"
**Verhalten:** Das bestehende „Erstellen"-Dropdown im ManagerView bekommt
einen dritten Eintrag „Neue Notiz …". Ein Dialogfenster öffnet sich mit:
- Auswahl eines Preset-PDFs aus `assets/presets/` (kleine Vorschau-Thumbnails,
  analog zur Thumbnail-Darstellung im ManagerView).
- Eingabe eines Namens für die neue Notiz.
- Bestätigung erstellt eine Kopie des gewählten Preset-PDFs im aktuell
  aktiven Ordner unter dem eingegebenen Namen und legt die zugehörige
  leere `.freenotes`-Datei an. Anschließend wird die Notiz direkt im Viewer
  geöffnet.  
**Neue Dateien:** `ui/popups/new_note_dialog.py`  
**Betroffene Dateien:** `ui/windows/manager_view.py`,
`ui/windows/manager_grid_mixin.py`, `core/library_manager.py`

---

## Phase 6 – Abschluss (zuletzt)

Diese Punkte erfordern, dass alle anderen Phasen abgeschlossen sind, da
sie die gesamte Oberfläche betreffen.

### 6.1 Lightmode vollständig überarbeiten
**Verhalten:** Alle QSS-Dateien mit `_light`-Suffix durchgehen und sicherstellen:
- Kein weißer Text auf weißem Hintergrund.
- Kein dunkler Hintergrund wo heller erwartet wird.
- Alle Komponenten die in den vorherigen Phasen neu hinzugekommen sind,
  ebenfalls mit Light-Variante versehen.
- `base_light.qss` als Referenz für Farbwerte verwenden.  
**Betroffene Dateien:** alle `*_light.qss`-Dateien,
`ui/popups/textbox_options_popup.py` (inline Styles),
`ui/popups/color_picker_popup.py` (inline Styles)

### 6.2 Alle UI-Strings in Sprachdateien auslagern
**Verhalten:**
- Alle deutschen Strings (Labels, Tooltips, Menüeinträge, Dialoge) in eine
  Datei `i18n/de.py` (oder `de.json`) auslagern.
- Englische Übersetzungen in `i18n/en.py` erstellen.
- Zentraler Zugriff über eine Hilfsfunktion `tr(key: str) -> str`, die
  anhand von `AppSettings.get_language()` die richtige Datei wählt.
- Die bestehende Sprachauswahl in `LanguagePage` speichert bereits die
  `language`-Einstellung; nach Neustart wird die neue Sprache geladen.  
**Hinweis:** Sehr umfangreiche Aufgabe – alle Dateien der Codebase betroffen.
Sinnvoll als letzter Schritt, wenn alle Features stabil sind.

---

## Zusammenfassung der Implementierungsreihenfolge

| Phase | Thema | Priorität |
|-------|-------|-----------|
| 1 | Kritische Bugfixes (Export-Crash, Z-Ebene, Radierer, Pfeile, Rotation) | 🔴 Kritisch |
| 2 | Interaktions-Bugfixes (Selektion, TextBox-Clipboard) | 🟠 Hoch |
| 3 | Neue Interaktionsfunktionen (Style-Änderung, Shift-Snap, Rotation Mehrfach) | 🟠 Hoch |
| 4 | Performance (Laden großer PDFs) | 🟡 Mittel |
| 5 | ManagerView Erweiterungen (Neue Notiz) | 🟡 Mittel |
| 6 | Lightmode + Lokalisierung | 🟢 Niedrig (zuletzt) |
