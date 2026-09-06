# Refactoring-Plan: Einheitliches Selection/Interaction-System

Dieses Dokument beschreibt das Konzept und den schrittweisen Entwicklungsplan zur Konsolidierung der Auswahl- und Transformationslogik in FreeNotes. Ziel ist es, die über verschiedene Klassen verstreute Handle-Logik in einer zentralen, robusten Overlay-Klasse zu vereinheitlichen.

> **Hinweis**: Dieser Plan basiert auf der Ist-Analyse in [`current_selection_state.md`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/docs/current_selection_state.md) und wurde nach einer kritischen Codebase-Review überarbeitet.

---

## 1. Ziel-Architektur (Target Design)

### 1.1 Das `SelectionBoxItem` (Unified Overlay)
* Anstatt dass jedes Item (`TextBoxItem`, `ShapeItem`, `ImageItem`) eigene Handles erzeugt und zeichnet, übernimmt eine einzige Klasse [`SelectionOverlayItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/selection_overlay_item.py) (umbenannt zu `SelectionBoxItem`) die komplette Interaktion für **Einzel- und Mehrfachauswahlen**.
* Das `SelectionBoxItem` liegt als einziges Overlay über den ausgewählten Elementen.
* Es beherbergt:
  * **8 Standard-Resize-Handles** (Ecken + Kantenmitten) für rechteckige Objekte, Bilder, Striche und Gruppen.
  * **1 Rotate-Handle** (z. B. oben oder unten positioniert).
  * **1 Options-Handle** (Copy / Cut / Delete Bar).
  * **Move-Funktionalität**: Verschieben durch Ziehen auf der Begrenzungslinie oder der optionalen Move-Pille.
* Es ersetzt **beide** existierenden Handle-Systeme:
  * **System A (Child-Handles)**: Die item-eigenen `ResizeHandleItem`, `MoveHandleItem`, `RotateHandleItem`, `OptionsHandleItem` in `TextBoxItem`, `ShapeItem`, `ImageItem` und deren Subklassen in [`shape_handles.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py) und [`image_handles.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py).
  * **System B (Szene-Level-Manager)**: Der [`BoundingBoxHandleManager`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/bounding_box_handle_manager.py), der 8 Handles als eigenständige Szene-Items für `StrokeItem`/`HighlightItem` verwaltet.

### 1.2 Beibehaltung der Sonderregeln & Modi
* **Linien & Pfeile (Linear Shapes)**:
  * Erkennt das `SelectionBoxItem`, dass ein einzelnes Linien- oder Pfeilobjekt ausgewählt ist, wechselt es in den **Linear-Modus**.
  * In diesem Modus werden **nur 2 Handles** gezeichnet, die direkt auf den Endpunkten liegen (kein Rotieren/Verschieben über separate Griffe nötig, da direkt manipulierbar).
  * **Wichtig**: Linien/Pfeile verwenden `start_point`/`end_point` statt einer Bounding-Rect. Das Interface (Abschnitt 2) berücksichtigt dies über das `ILinearItem`-Capability.
* **TextBox-Resize (Einzel-Selektion)**:
  * **Seitliches Resize (Word-Style)**: Zieht der Nutzer an den seitlichen Rändern einer einzelnen TextBox, ändert sich nur die Boxbreite. Der Text umbricht dynamisch neu (die Schriftgröße bleibt gleich).
  * **Eck-Resize**: Skaliert die TextBox-Rect proportional (Breite + Höhe). Text umbricht in der neuen Breite, Schriftgröße bleibt zunächst gleich.
* **TextBox in Gruppen-Resize**:
  * Die aktuelle `has_textbox`-Sperre in [`SceneSelectionMixin._on_selection_changed()`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/ui/scene/scene_selection.py) wird entfernt. TextBoxen nehmen am Gruppen-Resize teil.
  * **Phase 1 (Basis)**: Die TextBox-Rect wird proportional mitskaliert, Text umbricht neu. Schriftgröße bleibt gleich.
  * **Phase 2 (Optional/Späteres Feature)**: Proportionale Schriftgrößenskalierung (GoodNotes-Style). Dies ist komplex wegen Mixed Formatting im `QTextDocument` (verschiedene Schriftgrößen pro Absatz/Wort) und wird als separates Feature-Flag implementiert (siehe Phase 6).

### 1.3 Undo/Redo-Architektur (Unified Commands)
Um absolute Konsistenz zu gewährleisten und den `undo_stack` nicht zu korrumpieren, gelten folgende Regeln:

* **Transaktionale Commands**: Jegliche Manipulation über das `SelectionBoxItem` (Verschieben, Resizen, Rotieren) erzeugt erst beim *MouseReleaseEvent* genau **einen** zusammenhängenden Undo-Befehl.
* **Neues `TransformItemsCommand`**: Ein generischer Command ersetzt die fragmentierten typ-spezifischen Commands. Er speichert pro betroffenem Item einen typsicheren State-Snapshot (via `capture_state()` / `restore_state()`):
  ```python
  class TransformItemsCommand(QUndoCommand):
      def __init__(self, scene, description: str,
                   items_before: dict[QGraphicsItem, dict],
                   items_after:  dict[QGraphicsItem, dict]):
          # Jedes Snapshot-Dict enthält je nach Item-Typ:
          #   Alle:       pos (QPointF), rotation (float), transform_origin (QPointF)
          #   Rect-Items: rect (QRectF)
          #   Linear:     start_point (QPointF), end_point (QPointF)
          #   Path-Items: path (QPainterPath), [width (float)]
          #   TextBox:    font_size (float) [optional, für spätere Font-Skalierung]
          ...
  ```
* **Entkopplung**: Die Items selbst führen keine autonomen Undo-Befehle mehr während Handle-Interaktionen aus; diese Verantwortung liegt komplett beim steuernden `SelectionBoxItem`.
* **Bestehende Commands**: Die typ-spezifischen Commands (`ResizeShapeCommand`, `MoveImageCommand` etc.) werden in Phase 0 auf das `capture_state()`/`restore_state()`-Interface umgestellt und anschließend schrittweise durch `TransformItemsCommand` ersetzt.
* **Move-Pfad-Vereinheitlichung**: Es existieren derzeit 3 parallele Move-Pfade:
  1. Direkt-Drag im [`SelectionTool`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/tools/selection_tool.py) → `MoveItemsCommand`
  2. Item-eigene `*MoveHandle` → typ-spezifische Move-Commands
  3. Gruppen-`SelectionMoveHandle` → `MoveItemsCommand`
  
  **Lösung**: Pfad 2 entfällt (keine Item-eigenen MoveHandles mehr). Pfad 1 (SelectionTool-Drag für Einzel-Items) bleibt bestehen und nutzt `TransformItemsCommand`. Pfad 3 wandert ins neue `SelectionBoxItem`.

### 1.4 Ergänzende UX-Features für optimalen Komfort
* **Seitenverhältnis sperren (Shift-Lock)**: Halten der `Shift`-Taste sperrt das Seitenverhältnis (Aspect Ratio) beim Skalieren von Bildern, Formen und Gruppen.
* **Auto-Fit bei TextBoxen**: Ein Doppelklick auf die seitlichen Handles der TextBox passt die Breite automatisch an den längsten Textabschnitt an (verhindert unnötige Leerzeichen).
* **Rotierende Cursor**: Die Cursor-Richtungen (z. B. diagonal, horizontal) der Resize-Handles rotieren im Grafikraum mit dem Drehwinkel des ausgewählten Items mit, um Verwirrung bei gedrehten Objekten zu vermeiden.
* **Proportionales Linien-Skalieren in Gruppen**: Befindet sich eine Linie/Pfeil in einer Mehrfachauswahl, werden Start- und Endpunkt relativ zum Transformations-Zentrum skaliert, anstatt ein Bounding Box-Verzerrungsraster anzuwenden.

---

## 2. Das einheitliche Item-Interface (Capability-basiert)

Da die Item-Typen **fundamental unterschiedliche Geometrie-Modelle** verwenden (Rect vs. Endpunkte vs. Pfad), wird das Interface in ein Basis-Interface + optionale Capabilities aufgeteilt:

```python
from abc import ABC, abstractmethod
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QPainterPath

class IInteractiveItem(ABC):
    """Basis-Interface — alle auswählbaren Items müssen dies implementieren."""

    @abstractmethod
    def capture_state(self) -> dict:
        """Erzeugt einen Snapshot des aktuellen Zustands für Undo/Redo.
        Enthält mindestens: pos, rotation, transform_origin.
        Typ-spezifische Keys werden ergänzt (rect, points, path, etc.)."""
        ...

    @abstractmethod
    def restore_state(self, state: dict) -> None:
        """Stellt einen vorherigen Zustand aus einem Snapshot wieder her."""
        ...

    @abstractmethod
    def get_rotation_angle(self) -> float: ...

    @abstractmethod
    def set_rotation_angle(self, angle: float) -> None: ...

    @abstractmethod
    def get_transform_origin(self) -> QPointF: ...

    @abstractmethod
    def set_transform_origin(self, origin: QPointF) -> None: ...

    @abstractmethod
    def apply_scale(self, sx: float, sy: float, pivot: QPointF) -> None:
        """Skaliert das Item relativ zu einem Pivot-Punkt.
        Die Implementierung variiert je nach Item-Typ."""
        ...


class IRectResizable(IInteractiveItem):
    """Rect-basierte Items: TextBoxItem, ImageItem, rekt. ShapeItems."""

    @abstractmethod
    def get_geometry_rect(self) -> QRectF: ...

    @abstractmethod
    def set_geometry_rect(self, rect: QRectF) -> None: ...


class ILinearItem(IInteractiveItem):
    """Endpunkt-basierte Items: Linien, Pfeile."""

    @abstractmethod
    def get_start_point(self) -> QPointF: ...

    @abstractmethod
    def set_start_point(self, pt: QPointF) -> None: ...

    @abstractmethod
    def get_end_point(self) -> QPointF: ...

    @abstractmethod
    def set_end_point(self, pt: QPointF) -> None: ...


class IPathScalable(IInteractiveItem):
    """Pfad-basierte Items: StrokeItem, HighlightItem."""

    @abstractmethod
    def apply_bounding_box_resize(self, new_rect: QRectF) -> None:
        """Skaliert den internen Pfad auf eine neue Bounding-Rect."""
        ...
```

### Mapping auf bestehende Item-Klassen

| Item-Klasse | Implementiert | Bestehende Methoden (→ Mapping) |
| :--- | :--- | :--- |
| `StrokeItem` | `IPathScalable` | `boundingRect()` → `capture_state()`, `apply_bounding_box_resize()` ✅, `get_path_state()`/`set_path_state()` → `capture/restore_state()` |
| `HighlightItem` | `IPathScalable` | Identisch zu StrokeItem, zusätzlich `_style.width` im Snapshot |
| `TextBoxItem` | `IRectResizable` | `get_rect()` → `get_geometry_rect()`, `set_rect()` → `set_geometry_rect()`, `rotation()` → `get_rotation_angle()` |
| `ShapeItem` (Rect/Ellipse/Dreieck) | `IRectResizable` | `get_rect()` → `get_geometry_rect()`, `set_rect()` → `set_geometry_rect()` |
| `ShapeItem` (Linie/Pfeil) | `ILinearItem` | `start_point`/`end_point` Properties → `get/set_start_point()`/`get/set_end_point()` |
| `ImageItem` | `IRectResizable` | `get_rect()` → `get_geometry_rect()`, `set_rect()` → `set_geometry_rect()` |

---

## 3. Teilschritte (Step-by-Step Plan)

Da es sich um ein massives Refactoring handelt, teilen wir das Vorhaben in **7 logische Phasen** ein. Jede Phase ist so dimensioniert, dass sie innerhalb eines KI-Kontextfensters sicher und fehlerfrei umgesetzt werden kann.

### Phase 0: Command-Konsolidierung & State-Snapshots
> **Voraussetzung für alle folgenden Phasen.** Ohne einheitliche State-Snapshots kann das spätere `SelectionBoxItem` keine Undo-Operationen korrekt erzeugen.

* **Ziel**: Einführung von `capture_state()` / `restore_state()` auf allen Items und eines generischen `TransformItemsCommand`.
* **Schritte**:
  1. `capture_state() -> dict` und `restore_state(state: dict)` auf allen 5 Item-Typen implementieren:
     * `StrokeItem`: `{ "pos": QPointF, "path": QPainterPath }`
     * `HighlightItem`: `{ "pos": QPointF, "path": QPainterPath, "width": float }`
     * `TextBoxItem`: `{ "pos": QPointF, "rect": QRectF, "rotation": float, "transform_origin": QPointF }`
     * `ShapeItem` (Rect): `{ "pos": QPointF, "rect": QRectF, "rotation": float, "transform_origin": QPointF }`
     * `ShapeItem` (Linear): `{ "pos": QPointF, "start_point": QPointF, "end_point": QPointF, "rotation": float }`
     * `ImageItem`: `{ "pos": QPointF, "rect": QRectF, "rotation": float, "transform_origin": QPointF }`
  2. Neuen [`TransformItemsCommand`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/commands/) erstellen, der `{item: snapshot_dict}` vor/nach speichert und via `restore_state()` undo/redo ausführt.
  3. Bestehende typ-spezifische Commands (`ResizeShapeCommand`, `ResizeImageCommand`, `ResizeStrokeCommand`, `ResizeHighlightCommand`, `RotateShapeCommand`, `RotateImageCommand`) intern auf `capture_state()`/`restore_state()` umstellen. Die öffentliche API bleibt vorerst bestehen, damit das alte Handle-System weiterhin funktioniert.
  4. TextBox-Undo entkoppeln: Die inline Undo-Logik in `TextBoxItem._end_resize()` und den Handle-`mouseReleaseEvent()`-Methoden so refaktorieren, dass sie `capture_state()`/`restore_state()` nutzen statt direkt `set_rect()` zu callen.
* **Dateien**: Alle Item-Klassen in `items/`, neues `commands/transform_items_command.py`, bestehende Commands in `commands/`.
* **Validierung**: Alle bestehenden Interaktionen (Resize/Move/Rotate für jeden Item-Typ) müssen weiterhin funktionieren. Undo/Redo für jeden Interaktionstyp manuell testen.

---

### Phase 1: Interface-Definition & Adapter
* **Ziel**: Formalisierung des Capability-Interfaces auf allen Items, ohne die alte Interaktionslogik zu löschen.
* **Schritte**:
  1. ABC-Klassen `IInteractiveItem`, `IRectResizable`, `ILinearItem`, `IPathScalable` als Modul `items/interactive_item.py` anlegen.
  2. Item-Klassen die passenden Interfaces implementieren lassen:
     * `StrokeItem(QGraphicsItem, IPathScalable)` — `apply_bounding_box_resize()` existiert bereits
     * `HighlightItem(QGraphicsItem, IPathScalable)` — dito
     * `TextBoxItem(QGraphicsObject, IRectResizable)` — wrappen von `get_rect()`/`set_rect()`
     * `ShapeItem(QGraphicsItem, IRectResizable)` / `ShapeItem(QGraphicsItem, ILinearItem)` — dynamische Capability je nach Shape-Typ. Pragmatisch: `ShapeItem` implementiert beides, `SelectionBoxItem` prüft zur Laufzeit `shape_type`.
     * `ImageItem(QGraphicsItem, IRectResizable)` — wrappen von `get_rect()`/`set_rect()`
  3. Einheitliche Selection-Methode: `set_selected_custom(bool)` auf **allen** Items einführen (StrokeItem/HighlightItem haben derzeit nur `set_selected()`). Der alte Methodenname bleibt als Alias bestehen.
  4. `apply_scale(sx, sy, pivot)` auf allen Items implementieren — delegiert je nach Capability an `set_geometry_rect()`, `set_start/end_point()` oder `apply_bounding_box_resize()`.
* **Dateien**: Neues `items/interactive_item.py`, alle Item-Klassen in `items/`.
* **Validierung**: Unit-Tests für `capture_state()` → Modifikation → `restore_state()` Roundtrip auf jedem Item-Typ.

---

### Phase 2: Implementierung des neuen `SelectionBoxItem`
* **Ziel**: Erstellung des neuen, universellen Auswahl-Rahmens mit allen Handle-Typen.
* **Schritte**:
  1. [`SelectionOverlayItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/selection_overlay_item.py) zu `SelectionBoxItem` umbauen. Das bestehende `SelectionOverlayItem` hat bereits ~60% der Ziel-Funktionalität (8 Handles, Rotate, Move, Options für Multi-Selection). Es muss erweitert werden für:
     * **Einzel-Selektion**: Auch für 1 Item nutzbar (nicht nur Gruppen).
     * **Linear-Modus**: Erkennung von `ILinearItem` → Umschalten auf 2 Endpunkt-Handles.
     * **Capability-Dispatch**: `apply_scale()` nutzt das Interface statt isinstance-Checks.
  2. Implementierung der 8 Standard-Resize-Handles als Children des `SelectionBoxItem`. Bestehende `SelectionResizeHandle` als Basis.
  3. Rotate-Handle: Bestehende `SelectionRotateHandle` übernehmen.
  4. Options-Handle: Bestehende `SelectionOptionsHandle` übernehmen, Logik generalisieren (aktuell hat jeder Item-Typ eigene Copy/Cut/Delete-Logik in den Handle-Subklassen).
  5. Move-Handle: `SelectionMoveHandle` übernehmen.
  6. **Undo-Integration**: Alle Handle-Events nutzen `TransformItemsCommand` aus Phase 0. Ablauf: `mousePress` → `capture_state()` aller Items, `mouseRelease` → erneut `capture_state()`, push `TransformItemsCommand(before, after)`.
* **Dateien**: Umbau von `items/selection_overlay_item.py`, Wiederverwendung von `items/handle_item.py`, `items/rotate_handle_item.py`, `items/options_handle_item.py`, `items/move_handle_item.py`.
* **Validierung**: Isolierter Test des `SelectionBoxItem` mit jedem Item-Typ (einzeln + Gruppe). Undo/Redo für Resize, Rotate, Move, Delete.

---

### Phase 3: Szene & Tool Integration
> **Hinweis**: Dies ist die **komplexeste Phase**, da drei unabhängige Systeme zusammengeführt werden: `SceneSelectionMixin`, `SelectionTool` und `BoundingBoxHandleManager`.

* **Ziel**: Das `SelectionBoxItem` wird zum einzigen Interaktions-Overlay für alle Selection-Szenarien.
* **Schritte**:
  1. **`SceneSelectionMixin` umbauen** ([`scene_selection.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/ui/scene/scene_selection.py)):
     * `_on_selection_changed()` vereinfachen: Immer das `SelectionBoxItem` nutzen — egal ob 1 oder N Items.
     * **Kein `isinstance`-Dispatch mehr** zwischen Stroke/Highlight (→ BoundingBoxHandleManager) und TextBox/Shape/Image (→ item-eigene Handles). Stattdessen: `selection_box.attach(items)`.
     * **`has_textbox`-Sperre entfernen**: TextBoxen nehmen am Gruppen-Resize teil (Rect-Skalierung, zunächst ohne Font-Skalierung).
  2. **`BoundingBoxHandleManager` deaktivieren**:
     * In `PageScene.__init__()`: Erstellung des `BoundingBoxHandleManager` auskommentieren.
     * In `SceneSelectionMixin`: Alle `_bbox_handle_manager.attach()`/`.detach()`/`.reposition()` Aufrufe entfernen.
     * Die 8 `BoundingBoxHandle`-Szene-Items werden nicht mehr erzeugt.
  3. **Item-eigene Handles deaktivieren**:
     * `TextBoxItem.set_selected_custom(True)` darf keine Child-Handles mehr erzeugen (6 Resize + Move + Rotate + Options entfallen). Die Methode setzt nur noch den visuellen Selektions-Rahmen.
     * Analog für `ShapeItem.set_selected_custom()` und `ImageItem.set_selected_custom()`.
     * Der Body-Drag in `ShapeItem` (Linear-Modus) und `ImageItem` (selected-Drag) wird deaktiviert — das `SelectionBoxItem` übernimmt.
  4. **`SelectionTool` anpassen** ([`selection_tool.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/tools/selection_tool.py)):
     * Die Handle-Erkennung in `on_press()` muss die neuen Handle-Typen des `SelectionBoxItem` erkennen (statt `BoundingBoxHandle`, `ShapeResizeHandle` etc.).
     * **Direkter Item-Drag** (Pfad 1): Bleibt für Einzel-Items bestehen. Erzeugt `TransformItemsCommand` statt `MoveItemsCommand`.
     * **Gruppen-Drag**: Delegiert an `SelectionBoxItem` (Pfad 3).
  5. **Clipboard-Kompatibilität sicherstellen** ([`scene_clipboard.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/ui/scene/scene_clipboard.py)):
     * Copy/Paste klont Items. Wenn ein geklontes Item selektiert wird, muss `set_selected_custom(True)` korrekt funktionieren (keine Handles erzeugen, nur visueller Rahmen).
  6. **Eraser-Tool Edge-Case** ([`eraser_tool.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/tools/eraser_tool.py)):
     * Wenn ein Item gelöscht wird, das gerade im `SelectionBoxItem` referenziert ist: `SelectionBoxItem.on_item_removed(item)` muss das Item sauber aus der internen `_items`-Liste entfernen und die Handles neu positionieren (oder detachen, wenn kein Item mehr übrig).
* **Dateien**: `ui/scene/scene_selection.py`, `ui/scene/page_scene.py`, `tools/selection_tool.py`, `items/text_box_item.py`, `items/shape_item.py`, `items/image_item.py`, `ui/scene/scene_clipboard.py`.
* **Validierung**:
  * Einzel-Selektion für jeden Item-Typ: Handles erscheinen korrekt, Resize/Rotate/Move funktioniert, Undo/Redo korrekt.
  * Multi-Selektion (gemischt): Alle Item-Typen inklusive TextBox können gemeinsam skaliert/rotiert/verschoben werden.
  * Lasso-/Rect-Selection funktioniert.
  * TextBox-Doppelklick → Edit-Modus funktioniert.
  * Eraser während aktiver Selektion → kein Crash.
  * Copy/Paste → korrekte Selektion der eingefügten Items.

---

### Phase 4: Code-Cleanup
* **Ziel**: Vollständiges Löschen des toten Codes.
* **Schritte**:
  1. **Handle-Klassen löschen**:
     * `items/shape_handles.py` (komplett — `ShapeResizeHandle`, `ShapeMoveHandle`, `ShapeRotateHandle`, `ShapeOptionsHandle`)
     * `items/image_handles.py` (komplett — `ImageResizeHandle`, `ImageMoveHandle`, `ImageRotateHandle`, `ImageOptionsHandle`)
     * `items/bounding_box_handle_manager.py` (komplett — `BoundingBoxHandle`, `BoundingBoxHandleManager`)
  2. **Typ-spezifische Commands löschen/konsolidieren**:
     * `commands/move_shape_command.py`, `commands/move_image_command.py` → durch `TransformItemsCommand` ersetzt
     * `commands/resize_shape_command.py`, `commands/resize_image_command.py`, `commands/resize_stroke_command.py`, `commands/resize_highlight_command.py` → durch `TransformItemsCommand` ersetzt
     * `commands/rotate_shape_command.py`, `commands/rotate_image_command.py` → durch `TransformItemsCommand` ersetzt
     * `commands/move_items_command.py`, `commands/resize_items_command.py` → durch `TransformItemsCommand` ersetzt (sofern nirgends mehr referenziert)
     * `commands/__init__.py` Exports aktualisieren
  3. **Item-Klassen säubern**:
     * `TextBoxItem`: `_create_handles()`, `_update_handle_positions()`, `_set_handles_visible()`, Handle-bezogene Properties entfernen.
     * `ShapeItem`: Analog, plus alte Body-Drag-Logik (`mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` im selected-Modus).
     * `ImageItem`: Analog, plus Body-Drag-Logik.
     * Redundante Imports und auskommentierter Code entfernen.
  4. **Serialisierung prüfen** ([`freenotes_store.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/core/freenotes_store.py)):
     * `to_dict()` / `from_dict()` auf allen Items verifizieren — das Geometry-Interface darf die Persistenz nicht brechen.
  5. **PDF-Export prüfen** ([`pdf_exporter.py`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/core/pdf_exporter.py) und Sub-Exporter):
     * Die Exporter greifen direkt auf Item-Properties zu (`get_rect()`, `pos()`, `rotation()`). Sicherstellen, dass die neuen Interface-Methoden kompatibel sind oder die Exporter die alten Property-Namen weiterhin finden.
* **Dateien**: Alle oben genannten, `commands/__init__.py`, `items/__init__.py`.
* **Validierung**: Build ohne Fehler, keine toten Imports. Undo/Redo Regression-Test. Serialisierung Roundtrip (speichern → laden → alles noch da). PDF-Export eines Dokuments mit allen Item-Typen.

---

### Phase 5: UX-Polish
* **Ziel**: Feinschliff der visuellen Darstellung und Interaktionsqualität.
* **Schritte**:
  1. Einheitliche Hover-Animationen für alle Handles (Farb-Übergang, Größen-Pop).
  2. Farbschema: Modernisiertes HSL-Blau, konsistent über alle Handle-Typen.
  3. Rotierende Cursor: Die Cursor-Richtungen der Resize-Handles rotieren mit dem Drehwinkel des Items mit.
  4. Shift-Lock: Aspect-Ratio-Sperre beim Skalieren.
  5. Auto-Fit: Doppelklick auf seitliche TextBox-Handles passt Breite an Textinhalt an.
  6. Proportionales Linien-Skalieren in Gruppen: Start-/Endpunkt relativ zum Transformations-Zentrum skalieren.
* **Dateien**: `items/selection_overlay_item.py` (jetzt `SelectionBoxItem`), Handle-Klassen darin.

---

### Phase 6 (Optional): Proportionale Font-Skalierung für TextBoxen
> **Dieses Feature ist komplex und eigenständig.** Es wird bewusst als optionale Phase behandelt.

* **Ziel**: Bei Gruppen-Resize oder Eck-Resize einer einzelnen TextBox die Schriftgröße proportional mitskalieren (GoodNotes-Style).
* **Herausforderungen**:
  * `QTextDocument` hat Mixed Formatting — verschiedene Absätze/Wörter können verschiedene Schriftgrößen haben.
  * Proportionales Skalieren erfordert Iteration über alle `QTextBlock`s/`QTextFragment`s und Anpassung jeder einzelnen Schriftgröße.
  * Undo muss den gesamten formatierten HTML-Inhalt vor/nach sichern (großer Snapshot).
  * Die aktuelle [`TextBoxFormattingMixin`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/text_box_formatting.py) operiert auf Cursor-Selektion — es gibt keine Methode "skaliere alle Fonts um Faktor X".
* **Schritte**:
  1. `TextBoxItem.scale_all_fonts(factor: float)` implementieren — iteriert über Blocks/Fragments, skaliert jede Font-Size.
  2. `capture_state()` um `html_content` und `font_scale_factor` erweitern.
  3. Im `SelectionBoxItem`: Bei Eck-Resize mit TextBox `scale_all_fonts()` aufrufen.
  4. Feature-Flag in App-Settings, um zwischen Rect-Resize (Phase 3) und Font-Resize (Phase 6) umschalten zu können.
* **Dateien**: `items/text_box_item.py`, `items/text_box_formatting.py`, `items/selection_overlay_item.py`.

---

## 4. Zusammenfassung der betroffenen Dateien

| Datei | Phase | Art der Änderung |
| :--- | :--- | :--- |
| `items/interactive_item.py` | 1 | **NEU** — ABC-Interfaces |
| `items/stroke_item.py` | 0, 1 | `capture/restore_state()`, `IPathScalable` |
| `items/highlight_item.py` | 0, 1 | `capture/restore_state()`, `IPathScalable` |
| `items/text_box_item.py` | 0, 1, 3, 4 | `capture/restore_state()`, `IRectResizable`, Handle-Code entfernen |
| `items/shape_item.py` | 0, 1, 3, 4 | `capture/restore_state()`, `IRectResizable`/`ILinearItem`, Handle-Code entfernen |
| `items/image_item.py` | 0, 1, 3, 4 | `capture/restore_state()`, `IRectResizable`, Handle-Code entfernen |
| `items/selection_overlay_item.py` | 2, 3 | Umbau zu `SelectionBoxItem` |
| `items/handle_item.py` | 2 | Refactoring zur Basis-Handle-Klasse |
| `items/rotate_handle_item.py` | 2 | Generalisierung |
| `items/move_handle_item.py` | 2 | Generalisierung |
| `items/options_handle_item.py` | 2 | Generalisierung |
| `items/shape_handles.py` | 4 | **LÖSCHEN** |
| `items/image_handles.py` | 4 | **LÖSCHEN** |
| `items/bounding_box_handle_manager.py` | 3, 4 | Deaktivieren, dann **LÖSCHEN** |
| `commands/transform_items_command.py` | 0 | **NEU** |
| `commands/move_shape_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/resize_shape_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/rotate_shape_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/move_image_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/resize_image_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/rotate_image_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/resize_items_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `commands/move_items_command.py` | 0, 4 | Umstellen, dann **LÖSCHEN** |
| `ui/scene/scene_selection.py` | 3 | Kompletter Umbau |
| `ui/scene/page_scene.py` | 3 | BoundingBoxHandleManager entfernen |
| `tools/selection_tool.py` | 3 | Handle-Erkennung + Drag-Logik anpassen |
| `ui/scene/scene_clipboard.py` | 3 | Kompatibilitäts-Check |
| `tools/eraser_tool.py` | 3 | Edge-Case bei aktiver Selektion |
| `core/freenotes_store.py` | 4 | Verifizierung |
| `core/pdf_exporter.py` + Sub-Exporter | 4 | Verifizierung |
