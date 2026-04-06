# FreeNotes – Strukturierte Aufgabenliste

Geordnet nach Themengebiet, Abhängigkeiten und Implementierungsreihenfolge.
Punkte innerhalb einer Phase sollten in der angegebenen Reihenfolge umgesetzt
werden, da spätere Punkte häufig auf früheren aufbauen.

---

## Phase 1 – Kritische Bugfixes (Blockierend)

Diese Bugs verursachen Datenverlust oder machen grundlegende Funktionen
unbrauchbar. Sie müssen vor allem anderen behoben werden.

### 1.1 Seiten-Reorder: Reihenfolge springt zurück
**Problem:** Das Verschieben von Seiten per Drag & Drop in der Sidebar
verschiebt Annotationen zwar korrekt, die visuelle Seitenreihenfolge springt
danach aber wieder in den Ausgangszustand zurück.  
**Ursache:** `ReorderPagesCommand.redo()` überspringt den ersten Aufruf
(`_first_redo = True`), aber die direkte Anwendung in `SidebarWidget.dropEvent`
ruft `reorder_annotations` + `reorder_pages` + `rebuild_after_reorder` bereits
manuell auf. Dadurch wird beim nächsten Redo die Reihenfolge erneut angewendet
und der Zustand inkonsistent.  
**Fix:** Die manuelle Anwendung in `dropEvent` entfernen und stattdessen
`_first_redo = False` im Command setzen, sodass `undo_stack.push(cmd)` den
ersten `redo()`-Aufruf korrekt ausführt.  
**Betroffene Dateien:** `ui/bars/sidebar_widget.py`,
`commands/reorder_pages_command.py`

### 1.2 Annotationen nicht fest an Seite gebunden nach Reorder
**Problem:** Nach dem Verschieben von Seiten verlieren Annotationen (insbesondere
nach mehrfachem Undo/Redo) die Bindung an ihre korrekte Seite.  
**Fix:** `_page_index` der Items muss immer synchron mit der physischen Seite im
`doc_manager` gehalten werden. In `ScenePageManagerMixin.reorder_annotations`
sicherstellen, dass das finale `_page_index`-Mapping nach jedem Reorder-Zyklus
konsistent ist und nicht auf temporären `_old_page_index`-Attributen beruht.  
**Betroffene Dateien:** `ui/scene/scene_page_manager.py`

### 1.3 Tile-Renderer: Fehler bei Sidebar-Seitenoperationen
**Problem:** Bei Seite einfügen, duplizieren, verschieben und löschen rendert
der Tile-Renderer (virtuelle Seitendarstellung in `PageScene`) fehlerhaft –
Seiten zeigen falsche Inhalte oder Annotationen erscheinen an der falschen
Position.  
**Fix:** Nach jeder Seitenoperation müssen `_page_states`, `_page_y_offsets`,
`_rendered_set` und `_page_items` vollständig neu synchronisiert werden.
`rebuild_after_reorder` bereits korrekt aufgerufen; sicherstellen, dass der
virtuelle Render-Cache (`_placeholder_pm`, `_rendered_set`) nach jeder Operation
vollständig invalidiert wird.  
**Hinweis:** Direkt abhängig von 1.1 und 1.2 – erst nach deren Fix validieren.  
**Betroffene Dateien:** `ui/scene/page_scene.py`,
`ui/scene/scene_page_manager.py`

### 1.4 Seite duplizieren: Textmarker und Textboxen fehlen
**Problem:** `clone_page_annotations` in `ScenePageManagerMixin` klont nur Items,
die `to_dict` / `from_dict` korrekt implementieren. `HighlightItem` und
`TextBoxItem` werden zwar in der Methode referenziert, aber
`HighlightItem.from_dict` und `TextBoxItem.from_dict` existieren nicht als
Klassenmethoden – die Klonlogik schlägt still fehl.  
**Fix:** `from_dict`-Klassenmethoden für `HighlightItem` und `TextBoxItem`
implementieren (analog zu `StrokeItem` und `ShapeItem`), sodass
`clone_page_annotations` vollständig funktioniert. Alternativ: Clone über
`FreenotesStore._serialize_*` / `_deserialize_*` routen.  
**Betroffene Dateien:** `items/highlight_item.py`, `items/text_box_item.py`,
`ui/scene/scene_page_manager.py`

---

## Phase 2 – Datei- und Speicherverwaltung

Grundlegende Änderungen am Speichermodell. Diese Phase muss abgeschlossen sein,
bevor Autosave oder neue Dateioperationen hinzugefügt werden.

### 2.1 Automatisches Erstellen der .freenotes-Datei beim ersten Öffnen
**Verhalten:** Wenn eine PDF geöffnet wird und noch keine gleichnamige
`.freenotes`-Datei existiert, wird diese sofort angelegt (leere Struktur,
identisch zu `LibraryManager._create_empty_freenotes`).  
**Betroffene Dateien:** `ui/windows/viewer_file_io.py` (`open_pdf`)

### 2.2 Autosave nach jeder Aktion
**Verhalten:** Nach jedem Push auf den Undo-Stack wird die `.freenotes`-Datei
automatisch gespeichert (debounced, max. 1× pro Sekunde, um Schreiblast zu
begrenzen). Da die Datei nun immer existiert (→ 2.1), entfällt der
`freenotes_path is None`-Zweig.  
**Hinweis:** Der `is_modified`-Indikator (`•` im Titel) kann bleiben, um
anzuzeigen, ob der letzte Autosave erfolgreich war, oder entfernt werden – nach
Absprache.  
**Betroffene Dateien:** `ui/windows/viewer_file_io.py`,
`ui/windows/viewer_window.py`

### 2.3 „Speichern" und „Speichern unter" aus dem Three-Dot-Menu entfernen
**Voraussetzung:** 2.1 und 2.2 müssen fertig sein.  
**Verhalten:** Die Actions `_action_save` und `_action_save_as` aus
`ThreeDotMenu` entfernen. `_on_save` und `_on_save_as` aus `ViewerFileIOMixin`
entfernen. `set_save_enabled` entfällt.  
**Betroffene Dateien:** `ui/popups/three_dot_menu.py`,
`ui/windows/viewer_file_io.py`

### 2.4 Three-Dot-Menu: „Alle Annotationen löschen" (mit Undo)
**Verhalten:** Neuer Menüpunkt „Annotationen löschen …" mit Bestätigungsdialog.
Löscht alle Items aus der Scene und der `.freenotes`-Datei. Die Aktion ist per
Undo rückgängig machbar (neues `ClearAnnotationsCommand`, das den vollständigen
serialisierten Zustand speichert).  
**Betroffene Dateien:** `ui/popups/three_dot_menu.py`,
`ui/windows/viewer_file_io.py`, neues
`commands/clear_annotations_command.py`

### 2.5 Systemseitigen Papierkorb für Löschen im ManagerView verwenden
**Problem:** `LibraryManager._move_to_trash` versucht bereits `send2trash`,
fällt aber auf einen eigenen `_Papierkorb`-Ordner zurück. `send2trash` ist
nicht in `requirements.txt` gelistet.  
**Fix:** `send2trash` zu `requirements.txt` hinzufügen. Eigenen
`_Papierkorb`-Fallback entfernen. Beim Fehlen von `send2trash` eine klare
Fehlermeldung zeigen, statt still einen eigenen Ordner anzulegen.  
**Betroffene Dateien:** `requirements.txt`, `core/library_manager.py`

### 2.6 Umbenennen der PDF benennt .freenotes automatisch um
**Verhalten:** `LibraryManager.rename_document` benennt bereits beide Dateien
um und aktualisiert `pdf_path` in der `.freenotes`. Sicherstellen, dass nach
einem Umbenennen im ManagerView der in-memory `AppState.freenotes_path` und
der Titel im ViewerWindow (falls die Datei gerade geöffnet ist) ebenfalls
aktualisiert werden.  
**Betroffene Dateien:** `ui/windows/manager_view.py`,
`ui/windows/viewer_file_io.py`

### 2.7 Startzustand: ManagerView statt zuletzt geöffneter PDF laden, wenn vorher im ManagerView geschlossen
**Problem:** `AppSettings.get_last_opened_doc` speichert immer die zuletzt
geöffnete Datei, unabhängig davon, in welchem View das Programm geschlossen
wurde.  
**Fix:** Beim Schließen den aktiven View (`manager` oder `viewer`) in
`AppSettings` persistieren. Beim Start nur dann direkt in den Viewer wechseln,
wenn der gespeicherte Zustand `viewer` ist.  
**Betroffene Dateien:** `core/app_settings.py`,
`ui/windows/main_window.py`

---

## Phase 3 – Einstellungen und Persistenz

Kleine, weitgehend unabhängige Fixes, die aber früh erledigt werden sollten,
da sie direkten Einfluss auf das tägliche Nutzerverhalten haben.

### 3.1 Farbchip-Änderungen persistent speichern
**Verhalten:** Das angepasste Farbpaletten-Array (`_chip_colors` in
`ToolbarWidget`) wird bei jeder Änderung in `AppSettings` geschrieben
(analog zu `AppSettings.set_pen_colors`) und beim Start wiederhergestellt.  
**Betroffene Dateien:** `ui/bars/toolbar_widget.py`,
`core/app_settings.py`

### 3.2 Tool-Einstellungen aller Tools persistent speichern
**Verhalten:** `_tool_memory` in `ToolbarWidget` (Farbchip-Index + Width-Index
pro Tool) sowie der zuletzt aktive Tool-Name werden beim Beenden gespeichert
und beim Start wiederhergestellt.  
**Hinweis:** Eraser-Modus (`object`/`pixel`) und Selection-Modus
(`rect`/`lasso`) ebenfalls persistieren.  
**Betroffene Dateien:** `ui/bars/toolbar_widget.py`,
`core/app_settings.py`

### 3.3 Standard-Schriftgröße und Standard-Stifteinstellungen im Einstellungsfenster
**Problem:** `DisplayPage` speichert die Standard-Schriftgröße, aber
`TextBoxItem.__init__` liest sie nicht aus `AppSettings`. Die `PenPage`
speichert Farbe und Breite, aber `ToolbarWidget` initialisiert sich mit
eigenen Defaults ohne `AppSettings` zu befragen.  
**Fix:**
- `TextBoxItem.__init__` liest `AppSettings.get_default_font_size()` als
  Fallback für `style.font_size`.
- `ToolbarWidget.__init__` initialisiert `_chip_colors` aus
  `AppSettings.get_pen_colors()` (bereits implementiert) und setzt den
  aktiven Chip auf `AppSettings.get_pen_default_color()`.
- Nach einer Änderung in `PenPage` werden die `_chip_colors` und der
  angezeigte Chip im laufenden `ToolbarWidget` sofort aktualisiert.  
**Betroffene Dateien:** `items/text_box_item.py`,
`ui/bars/toolbar_widget.py`,
`ui/windows/settings_pages/pen_page.py`

---

## Phase 4 – Clipboard-Überarbeitung

Eigenständige, klar abgegrenzte Änderung ohne Abhängigkeiten zu Phase 1–3.

### 4.1 Systemclipboard für Text-Einfügen in Textboxen
**Verhalten:** Beim Drücken von Strg+V in einer aktiven `TextBoxItem`-Session
wird zuerst `QApplication.clipboard().text()` geprüft. Falls dort Text
vorliegt, wird dieser eingefügt (plain text, Formatierung der aktuellen
Cursor-Position übernehmen). Eigene Annotations-Clipboard-Einträge
(`AppState.items_clipboard`) haben Vorrang: Wenn der Systemclipboard leer ist
und `items_clipboard` gefüllt, wird wie bisher eingefügt.  
**Hinweis:** Das Kopieren von Annotationen (Striche, Formen, Textboxen als
Objekte) bleibt intern über `AppState.items_clipboard`; der Systemclipboard
wird dabei *nicht* beschrieben, da binäre Grafikobjekte systemübergreifend
nicht sinnvoll sind.  
**Betroffene Dateien:** `items/text_box_input.py`,
`ui/scene/scene_clipboard.py`

---

## Phase 5 – Bugfixes an bestehenden Werkzeugen

### 5.1 Selection-Box von Formen (Rechteck, Rounded Rect, Kreis, Dreieck)
**Problem A – Resize-Handles liegen auf der gestrichelten Linie:**  
`ShapeItem.boundingRect` erweitert den Bereich bei Selektion um ±50/60/40 px,
aber `_update_handle_positions` platziert Handles direkt auf den
`_rect`-Kanten. Die gestrichelte Linie in `_paint_selection` wird mit
`pad = stroke_width / 2 + 3` gezeichnet – Handles müssen dieselbe
Außenposition erhalten.  
**Fix:** Handle-Positionen um `pad` nach außen verschieben, analog zu
`TextBoxItem`.

**Problem B – Move-Handle-Klick ohne Funktion:**  
`ShapeMoveHandle.mouseReleaseEvent` ruft `box.show_options_popup()` auf, aber
nur wenn `_click_only` und nicht `_dragging`. `_click_only` wird in
`mousePressEvent` auf `True` gesetzt, aber `ShapeMoveHandle` erbt von
`MoveHandleItem`, das dieses Flag korrekt setzt. Prüfen, ob
`_drag_start_box_pos` korrekt initialisiert wird und die Threshold-Logik
greift.

**Problem C – Rotate-Handle nicht anklickbar:**  
`ShapeRotateHandle` erbt von `RotateHandleItem`. Dessen `shape()`-Methode
fehlt (nur `boundingRect` definiert), daher ist der Klick-Bereich auf den
exakten Pixelbereich des gezeichneten Kreises beschränkt.  
**Fix:** `shape()`-Methode in `RotateHandleItem` hinzufügen, die einen
größeren Klickbereich (Radius + 8 px) zurückgibt – identisch zur
`shape()`-Methode in `ResizeHandleItem`.  
**Betroffene Dateien:** `items/shape_item.py`, `items/shape_handles.py`,
`items/rotate_handle_item.py`

---

## Phase 6 – Hand-Tool als universelles Cursor-Tool + Selection-Tool Ergänzungen

### Konzept: Zwei komplementäre Interaktions-Tools

Das **Hand-Tool** wird zum universellen „Cursor-Tool" ausgebaut – dem Standard-
Tool, das der Nutzer immer aktiv haben kann, ohne in einen spezialisierten Modus
wechseln zu müssen. Es deckt alle alltäglichen Interaktionen ab: navigieren,
einzelne Annotationen anfassen, und per Rechtsklick auf alles reagieren. Es
braucht keine Präzisions-Auswahl und kein Bounding-Box-Resize.

Das **Selection-Tool** bleibt das spezialisierte Werkzeug für Mehrfachauswahl,
Lasso, präzises Bounding-Box-Resize und Bulk-Operationen. Es bekommt dieselben
Rechtsklick-Funktionen wie das Hand-Tool, da ein Nutzer im Selection-Modus
ebenfalls Annotationen per Rechtsklick bearbeiten möchte.

Die Phase-5-Fixes (Form-Selection-Handles) sind Voraussetzung für 6.2 und 6.3.

---

### 6.1 Hand-Tool: Einzelne Annotationen per Klick auswählen und verschieben

**Aktueller Zustand:** Das Hand-Tool erkennt bereits einen Klick auf
selektierbare Items (`_get_selectable_types`) und ruft `scene.set_selection`
auf. Drag auf leerer Fläche löst Kamera-Pan aus. Das Grundgerüst ist also
vorhanden.

**Fehlende Verhaltensweisen:**
- Klick auf eine Annotation → Item wird selektiert, seine Handles (Move,
  Resize, Rotate) erscheinen, genau wie beim Selection-Tool.
- Drag auf einer bereits selektierten Annotation → Item wird verschoben
  (MoveItemsCommand, analog zu `SelectionTool._finish_drag`).
- Klick auf leere Fläche → Selektion aufheben + Kamera-Pan (bereits
  funktioniert).
- Shift+Klick → Annotation zur Selektion hinzufügen / entfernen (bereits
  implementiert).
- Das Hand-Tool soll **keine** Rechteck- oder Lasso-Auswahl starten – das
  bleibt exklusiv dem Selection-Tool. Drag auf leerer Fläche = immer Pan.

**Technische Umsetzung:** In `HandTool.on_press` den Drag-Threshold-Check
ergänzen: Wenn beim Move ein Item getroffen war (`_click_was_on_item`), soll
die Bewegung als Item-Drag interpretiert werden (Positions-Delta auf alle
`_selected_items` anwenden). In `on_release` ein `MoveItemsCommand` pushen,
falls Items bewegt wurden.

**Betroffene Dateien:** `tools/hand_tool.py`

---

### 6.2 Hand-Tool und Selection-Tool: Rechtsklick-Kontextmenü auf Annotationen

**Verhalten (beide Tools identisch):**
Rechtsklick auf eine beliebige Annotation öffnet ein kontextuelles Menü:
- „Kopieren" (Strg+C)
- „Ausschneiden" (Strg+X)
- „Löschen" (Entf)

Rechtsklick auf eine **Textbox** zeigt zusätzlich:
- „Bearbeiten" → startet den Bearbeitungsmodus (entspricht Doppelklick)

Das Menü gilt für das Item unter dem Cursor. Wenn das geklickte Item nicht
in der aktuellen Selektion liegt, wird es zunächst einzeln selektiert, bevor
das Menü erscheint. Wenn mehrere Items selektiert sind und eines davon
Rechtsklick erhält, gelten die Aktionen für alle selektierten Items (Bulk).

**Aktueller Zustand beim Selection-Tool:** `_show_context_menu` ist bereits
implementiert, aber schließt Textboxen bei Einzelauswahl aus und zeigt das
Menü nur bei aktiver Selektion. Diese Einschränkungen entfernen.

**Technische Umsetzung:**
- Eine gemeinsame Hilfsmethode `_build_annotation_context_menu(scene, pos)`
  in einem neuen Mixin `tools/tool_context_menu.py` oder direkt als
  Standalone-Funktion implementieren, die von beiden Tools aufgerufen wird.
- `HandTool.on_press` für `Qt.MouseButton.RightButton` erweitern.
- `SelectionTool._show_context_menu` auf die gemeinsame Methode umrouten.

**Betroffene Dateien:** `tools/hand_tool.py`, `tools/selection_tool.py`,
neues `tools/tool_context_menu.py` (optional, je nach Umfang)

---

### 6.3 Hand-Tool und Selection-Tool: Rechtsklick auf freie Fläche

**Verhalten (beide Tools identisch):**
Rechtsklick auf eine leere Fläche (kein Item getroffen) öffnet ein Menü:
- „Einfügen" (Strg+V) – nur aktiv, wenn `AppState.items_clipboard` gefüllt
  oder Systemclipboard ein Bild enthält (→ nach Phase 4 und 8)
- „Bild einfügen …" – öffnet Dateidialog (PNG, JPG, JPEG, WEBP);
  Voraussetzung für Phase 8 (ImageItem), daher zunächst als deaktivierter
  Platzhalter einfügbar

**Hinweis:** „Bild einfügen" wird erst nach Abschluss von Phase 8 vollständig
funktionieren. Der Menüpunkt kann bereits in Phase 6 angelegt, aber mit einem
`TODO`-Guard versehen werden.

**Betroffene Dateien:** `tools/hand_tool.py`, `tools/selection_tool.py`

---

### 6.4 Hand-Tool: Doppelklick auf Textbox startet Bearbeitungsmodus

**Aktueller Zustand:** `PageScene.mouseDoubleClickEvent` leitet bei aktivem
Selection-Tool einen Doppelklick auf Textboxen an `item.mousePressEvent` weiter
und emittiert `tool_switch_requested("text")`. Beim Hand-Tool fehlt diese
Logik.

**Verhalten:** Doppelklick auf eine `TextBoxItem` mit aktivem Hand-Tool startet
direkt den Inline-Bearbeitungsmodus, ohne das aktive Tool auf „Text" zu
wechseln. Der Nutzer bleibt im Hand-Tool – er verlässt den Bearbeitungsmodus
durch Klick außerhalb der Textbox (wie heute beim Text-Tool).

**Technische Umsetzung:** In `HandTool` eine `on_double_click`-Methode
ergänzen (oder in `PageScene.mouseDoubleClickEvent` den Check auf Hand-Tool
ausweiten). `BaseTool` um eine optionale `on_double_click`-Methode erweitern,
die standardmäßig ein No-Op ist.

**Betroffene Dateien:** `tools/hand_tool.py`, `tools/base_tool.py`,
`ui/scene/page_scene.py`

---

## Phase 7 – ManagerView Verbesserungen

Alle Änderungen am ManagerView sind weitgehend unabhängig voneinander und
können parallel entwickelt werden. Die Reihenfolge innerhalb dieser Phase
ist nach Aufwand/Relevanz sortiert.

### 7.1 Dropdown-Pfeil der Ordner zu groß
**Problem:** Der Chevron `▶` / `▼` vor Ordnernamen in `_make_sidebar_item` ist
ein Unicode-Zeichen, dessen Größe von der System-Schriftart abhängt.  
**Fix:** Unicode-Zeichen durch ein kleines Lucide-Icon (`chevron_right` /
`chevron_down`, Größe 10–12 px) ersetzen, das über `IconFactory.create`
erzeugt wird.  
**Betroffene Dateien:** `ui/windows/manager_view.py`

### 7.2 Schließen eines übergeordneten Ordners klappt Unterordner nicht ein
**Problem:** `_expanded_folders` ist ein flaches Set. Beim Entfernen eines
übergeordneten Ordners aus dem Set bleiben Unterordner darin erhalten und
werden beim nächsten Aufklappen wieder angezeigt.  
**Fix:** Beim Schließen eines Ordners rekursiv alle Kind-Ordner aus
`_expanded_folders` entfernen (via `LibraryManager.get_all_folders` filtern).  
**Betroffene Dateien:** `ui/windows/manager_view.py`

### 7.3 Ordner-Rechtsklickmenü: Löschen und Umbenennen
**Verhalten:**
- Rechtsklick auf Ordner in der Sidebar öffnet Kontextmenü mit „Umbenennen"
  und „Löschen".
- Beim Löschen nicht-leerer Ordner: Sicherheitsabfrage
  (QMessageBox mit Anzahl enthaltener Dokumente).
- Löschen verwendet `send2trash` (→ 2.5 ist Voraussetzung).  
**Betroffene Dateien:** `ui/windows/manager_view.py`,
`core/library_manager.py`

### 7.4 Einzelauswahl per Klick auf Thumbnail + Aktionsleiste
**Verhalten:** Einzelklick auf ein PDF-Thumbnail selektiert es (visueller
Rahmen, analog zu `ThumbnailCard.set_active`). Eine kontextbezogene
Aktionsleiste oder ein Kontextmenü erscheint mit: Löschen, Verschieben (in
Ordner wählen), Exportieren (als annotierte PDF), Duplizieren, Umbenennen.  
**Hinweis:** Das bestehende Rechtsklick-Menü (`contextMenuEvent` in `PdfCard`)
wird durch diese Einzelauswahl-Logik ersetzt / erweitert. Der alte
Rechtsklick-Handler in `PdfCard` (nur Umbenennen/Löschen) wird entfernt.  
**Betroffene Dateien:** `ui/components/pdf_card.py`,
`ui/windows/manager_view.py`

### 7.5 Mehrfachauswahl im ManagerView über „Haken-Tool"
**Verhalten:** Neues auswählbares Tool in der ManagerView-Toolbar (Lucide-Icon
`check_square` o. ä., über `IconFactory` registriert). Beim Aktivieren: alle
anderen UI-Elemente außer den Thumbnails werden ausgegraut. Jedes Thumbnail
zeigt eine Checkbox. Funktionen auf Mehrfachauswahl: Löschen, Verschieben
(Ordner wählen), Exportieren als ZIP, Alle auswählen (Strg+A).  
**Hinweis:** 7.4 sollte vorher fertig sein, da beide die Selektionslogik in
`PdfCard` teilen.  
**Betroffene Dateien:** `ui/components/pdf_card.py`,
`ui/windows/manager_view.py`, `ui/components/icon_factory.py`

---

## Phase 8 – Neue Annotationstypen

### 8.1 Bild-Annotation (ImageItem)
**Verhalten:**
- Einfügen über Drag & Drop aus dem Explorer in den ViewerWindow.
- Einfügen über Strg+V, wenn der Systemclipboard ein Bild enthält
  (QApplication.clipboard().image()).
- Einfügen über Rechtsklick → „Bild einfügen" im Hand-Tool oder Selection-Tool (→ 6.3).
- Unterstützte Formate: PNG, JPG, JPEG, WEBP.
- Neues `ImageItem(QGraphicsObject)` mit denselben Handles wie `ShapeItem`
  (Resize, Move, Rotate) über `ShapeResizeHandle` / `ShapeMoveHandle` /
  `ShapeRotateHandle`.
- Z-Wert: Unterhalb aller anderen Annotationen (zwischen PDF-Seite = 0 und
  Highlights = 5), z. B. Z-Wert 2.
- Serialisierung: Bild-Daten als Base64 in `.freenotes` gespeichert, inkl.
  Position, Größe, Rotation und `page_index`.
- Undo/Redo: `AddItemCommand` / `RemoveItemCommand` (ggf. generalisieren).
- Export: In `PdfExporter` über neuen `PdfImageExporter` – `page.insert_image`
  von PyMuPDF verwenden.  
**Neue Dateien:** `items/image_item.py`, `core/pdf_image_exporter.py`  
**Betroffene Dateien:** `items/__init__.py`, `commands/__init__.py`,
`ui/scene/scene_registry.py`, `ui/scene/scene_clipboard.py`,
`core/freenotes_store.py`, `core/pdf_exporter.py`,
`tools/selection_tool.py`, `ui/windows/viewer_window.py`

---

## Phase 9 – PDFViewer Erweiterungen

### 9.1 Seitentitel im Viewer per Doppelklick umbenennen
**Verhalten:** Doppelklick auf `_title_label` im `ViewerWindow` macht das Label
editierbar (QLineEdit, das über dem Label eingeblendet wird, oder direktes
Umwandeln in ein `QLineEdit`). Bestätigung per Enter oder Fokus-Verlust.
Umbenennung wird auf Dateisystem-Ebene durchgeführt (→ 2.6). Undo/Redo: Ein
neues `RenameDocumentCommand` wrappt die Umbenennung.  
**Betroffene Dateien:** `ui/windows/viewer_window.py`,
`ui/windows/viewer_file_io.py`, neues
`commands/rename_document_command.py`

### 9.2 Seiten in der Sidebar kopieren und in andere PDFs einfügen
**Verhalten:**
- Rechtsklick auf eine Seite in der Sidebar → „Seite kopieren" oder Strg+C
  (wenn Sidebar-Fokus aktiv).
- Kopierte Seite wird als Kombination aus PDF-Seitendaten (Bytes via
  `doc_manager.save_page_bytes`) und serialisierten Annotationen im
  `AppState` zwischengespeichert (neues `page_clipboard`-Attribut,
  unabhängig vom bestehenden `items_clipboard`).
- Einfügen: Rechtsklick → „Seite einfügen" oder Strg+V (wenn Sidebar-Fokus).
  Neue Seite wird unterhalb der aktuell ausgewählten Sidebar-Seite eingefügt.
  Funktioniert auch für Einfügen in andere geöffnete PDFs (falls zukünftig
  Multi-Tab), im Moment nur in der aktuellen PDF.
- Undo/Redo: Über `AddPageCommand` (bereits vorhanden) mit
  `page_bytes`-Erweiterung.  
**Betroffene Dateien:** `app/app_state.py`,
`ui/bars/sidebar_widget.py`,
`commands/add_page_command.py`

---

## Phase 10 – Code-Qualität und Bereinigung

Diese Phase kann parallel zu anderen Phasen stattfinden, sollte aber nicht
als letztes aufgeschoben werden, da technische Schulden die Arbeit in allen
anderen Phasen erschweren.

### 10.1 Toten und ungenutzten Code entfernen
**Kandidaten (nach Analyse der Codebase):**
- `tmp_refactor_ui.py` – Einmal-Skript, kann entfernt werden.
- `count_lines.py` – Hilfsskript, kann entfernt werden.
- `styles/dark_theme.qss` – Leer, wird nicht mehr geladen; entfernen.
- `styles/textbox.qss` und `styles/textbox_light.qss` – Nur Kommentare, kein
  aktiver CSS; entweder befüllen oder entfernen.
- `ViewerFileIOMixin._fallback_open_pdf_setup` – Wird nach Autosave (→ 2.2)
  nicht mehr in zwei Varianten benötigt; vereinfachen.
- `AppState.reset()` – Wird nirgendwo aufgerufen; entfernen oder
  dokumentieren.
- `base.qss`: `#viewerWindow { background-color: #862d2dff; }` – Offensichtlich
  ein Debug-Artefakt (rötlicher Hintergrund); auf korrekten Wert setzen.  
**Betroffene Dateien:** diverse

---

## Phase 11 – Abschluss (zuletzt)

Diese Punkte erfordern, dass alle anderen Phasen abgeschlossen sind, da
sie die gesamte Oberfläche betreffen.

### 11.1 Lightmode vollständig überarbeiten
**Verhalten:** Alle QSS-Dateien mit `_light`-Suffix durchgehen und sicherstellen:
- Kein weißer Text auf weißem Hintergrund.
- Kein dunkler Hintergrund wo heller erwartet wird.
- Alle Komponenten die in Phase 1–10 neu hinzugekommen sind ebenfalls mit
  Light-Variante versehen.
- `base_light.qss` als Referenz für Farbwerte verwenden.  
**Betroffene Dateien:** alle `*_light.qss`-Dateien,
`ui/popups/textbox_options_popup.py` (inline Styles),
`ui/popups/color_picker_popup.py` (inline Styles)

### 11.2 Alle UI-Strings in Sprachdateien auslagern
**Verhalten:**
- Alle deutschen Strings (Labels, Tooltips, Menüeinträge, Dialoge) in eine
  Datei `i18n/de.py` (oder `de.json`) auslagern.
- Englische Übersetzungen in `i18n/en.py` erstellen.
- Zentraler Zugriff über eine Hilfsfunktion `tr(key: str) -> str`, die
  anhand von `AppSettings.get_language()` die richtige Datei wählt.
- Die bestehende Sprachauswahl in `LanguagePage` bereits die `language`-
  Einstellung speichert; nach Neustart wird die neue Sprache geladen.  
**Hinweis:** Sehr umfangreiche Aufgabe – alle Dateien der Codebase betroffen.
Sinnvoll als letzter Schritt, wenn alle Features stabil sind.

---

## Zusammenfassung der Implementierungsreihenfolge

| Phase | Thema | Priorität |
|-------|-------|-----------|
| 1 | Kritische Bugfixes (Seiten-Reorder, Duplikation, Tile-Renderer) | 🔴 Kritisch |
| 2 | Datei- und Speicherverwaltung (Autosave, Papierkorb, Umbenennen) | 🔴 Kritisch |
| 3 | Einstellungen und Persistenz | 🟠 Hoch |
| 4 | Clipboard-Überarbeitung | 🟠 Hoch |
| 5 | Bugfixes an bestehenden Werkzeugen (Form-Selection) | 🟠 Hoch |
| 6 | Hand-Tool als universelles Cursor-Tool + Selection-Tool Rechtsklick | 🟡 Mittel |
| 7 | ManagerView Verbesserungen | 🟡 Mittel |
| 8 | Bild-Annotation (ImageItem) | 🟡 Mittel |
| 9 | PDFViewer Erweiterungen (Titelumbenennung, Seitenclipboard) | 🟡 Mittel |
| 10 | Code-Qualität / Bereinigung | 🟢 Niedrig (laufend) |
| 11 | Lightmode + Lokalisierung | 🟢 Niedrig (zuletzt) |
