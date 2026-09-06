# Analyse des aktuellen Selection/Interaction-Systems in FreeNotes

Diese Dokumentation beschreibt den aktuellen Ist-Zustand (Stand: Juli 2026) bezüglich der Auswahl (Selection), des Verschiebens (Move), der Größenänderung (Resize), der Rotation (Rotate) und der Mehrfachauswahl (Multi-Selection) für alle fünf Annotationstypen.

---

## 1. Übersicht der Item-Typen und deren Interaktions-Klassen

| Annotationstyp | Daten/Darstellungs-Klasse | Steuerung / Handles | Rotierbar | Resize-Art |
| :--- | :--- | :--- | :--- | :--- |
| **Stroke (Stift)** | [`StrokeItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/stroke_item.py) | Scene-level [`BoundingBoxHandleManager`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/bounding_box_handle_manager.py) | Nein (nur in Gruppe) | Pfadskalierung |
| **Highlight (Marker)** | [`HighlightItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/highlight_item.py) | Scene-level [`BoundingBoxHandleManager`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/bounding_box_handle_manager.py) | Nein (nur in Gruppe) | Pfadskalierung |
| **TextBox (Text)** | [`TextBoxItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/text_box_item.py) | Eigene Child-Items ([`ResizeHandleItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/handle_item.py), Move/Rotate/Options) | Ja | Bounding-Box Resize (Textumfluss) |
| **Shape (Formen)** | [`ShapeItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_item.py) | Eigene Child-Items ([`ShapeResizeHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py) etc.) | Ja | Geometrische Anpassung (z.B. Radien, Endpunkte) |
| **Image (Bilder)** | [`ImageItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_item.py) | Eigene Child-Items ([`ImageResizeHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py) etc.) | Ja | Bildskalierung |

---

## 2. Detaillierte Analyse nach Annotationsart

### 2.1 StrokeItem (Freihand-Zeichnung) & HighlightItem (Text-Marker)
Diese beiden Typen teilen sich denselben Interaktionsmechanismus über die Szene.
* **Klassen**:
  * [`StrokeItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/stroke_item.py)
  * [`HighlightItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/highlight_item.py)
  * [`BoundingBoxHandleManager`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/bounding_box_handle_manager.py)
  * [`SelectionTool`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/tools/selection_tool.py)
* **Auswahl (Selection)**:
  * Durch Klick oder Lasso-/Rechteck-Auswahl im `SelectionTool`.
  * Das Item erhält kein natives Qt-Auswahlsignal, sondern `set_selected(True)` wird aufgerufen.
  * Das Item zeichnet in `paint()` einen gestrichelten Rahmen (`#3B7BF5`, Dash-Pattern `[6, 4]`) um seine eigene `boundingRect()`.
* **Verschieben**:
  * Wird durch Ziehen auf dem Item im `SelectionTool` ausgeführt. Position wird via `setPos()` aktualisiert.
* **Größenänderung (Resize)**:
  * Der globale `BoundingBoxHandleManager` in `PageScene` klinkt sich ein und blendet 8 kreisförmige Handles (`tl`, `tc`, `tr`, `ml`, `mr`, `bl`, `bc`, `br`) ein.
  * Dragging berechnet die neue Bounding-Box und ruft `apply_bounding_box_resize(new_br)` auf.
  * Intern wird der zugrundeliegende `QPainterPath` im lokalen Koordinatensystem skaliert.
* **Rotation**:
  * **Nicht unterstützt** als Einzel-Selektion. Es existiert kein Rotations-Handle für einzelne Strokes/Highlighters.
* **Mehrfachauswahl**:
  * Mehrere Strokes/Highlighters werden über [`SelectionOverlayItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/selection_overlay_item.py) gruppiert.
  * Die Gruppe kann verschoben, skaliert und **rotiert** werden (über den Gruppen-Rotations-Handle `SelectionRotateHandle`). Bei der Gruppenrotation wird der Pfad jedes einzelnen Items im Szene-Koordinatensystem rotiert.

---

### 2.2 TextBoxItem (Textfeld)
Textfelder verwalten ihre Interaktionsobjekte vollständig selbst als Child-GraphicsItems.
* **Klassen**:
  * [`TextBoxItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/text_box_item.py)
  * [`ResizeHandleItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/handle_item.py)
  * [`MoveHandleItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/move_handle_item.py)
  * [`RotateHandleItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/rotate_handle_item.py)
  * [`OptionsHandleItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/options_handle_item.py)
* **Auswahl (Selection)**:
  * Die Szene ruft `set_selected_custom(True)` auf.
  * Die TextBox zeigt ihre eigenen Handles an: 6 Resize-Handles an den Ecken und den linken/rechten Rändern (keine oben/unten mittig, da dort Move/Rotate liegen).
  * Ein blauer Rahmen wird über das Paint-Event gerendert.
* **Verschieben**:
  * Ausschließlich über das obere, pillenförmige **MoveHandleItem** (`III` Symbol). Normales Dragging auf dem Text startet stattdessen die Textauswahl (Editing-Modus).
* **Größenänderung (Resize)**:
  * Über die 6 `ResizeHandleItem`s. Bei Änderung wird die Textbreite des `QTextDocument` angepasst, was zu automatischem Zeilenumbruch führt.
* **Rotation**:
  * Über das untere **RotateHandleItem** (`↻` Symbol). Das Textfeld rotiert um seinen Mittelpunkt (wird temporär als `transformOriginPoint` gesetzt).
* **Mehrfachauswahl**:
  * Sobald ein `TextBoxItem` Teil einer Mehrfachauswahl ist, wird das Skalieren der gesamten Gruppe **komplett deaktiviert** (`SceneSelectionMixin._on_selection_changed` ruft `detach()` auf, wenn `has_textbox` True ist).
  * Die Gruppe kann nur gemeinsam verschoben oder über das Gruppen-Rotations-Handle rotiert werden.

---

### 2.3 ShapeItem (Geometrische Formen)
Unterstützt 6 Formen (Ellipse, Rechteck, Dreiecke, Linien, Pfeile). Verwendet eine eigene Ableitung der TextBox-Handles.
* **Klassen**:
  * [`ShapeItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_item.py)
  * [`ShapeResizeHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py)
  * [`ShapeMoveHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py)
  * [`ShapeRotateHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py)
  * [`ShapeOptionsHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/shape_handles.py)
* **Auswahl (Selection)**:
  * Szene ruft `set_selected_custom(True)` auf. Aktiviert die Sichtbarkeit der eigenen Handles.
* **Verschieben**:
  * Über das eigene `ShapeMoveHandle` (Pille oben) oder durch Klicken/Ziehen auf der gefüllten Fläche (sofern gefüllt).
* **Größenänderung (Resize)**:
  * **Rechteckige Formen**: Nutzen 6 Handles (Corners + Mid-Left / Mid-Right).
  * **Linien/Pfeile**: Haben eine eigene Auswahlart. Sie nutzen nur **2 Endpunkt-Handles** (gekennzeichnet als `_is_endpoint = True`, größere ausgefüllte Kreise). Das Verschieben dieser passt direkt den Start- bzw. Endpunkt der Linie an, ohne das gesamte Bounding Box-Verhältnis zu verzerren.
* **Rotation**:
  * Über das eigene `ShapeRotateHandle` (unten). Linien/Pfeile benötigen dies theoretisch nicht (da die Endpunkte frei verschoben werden können), besitzen es aktuell aber standardmäßig.
* **Mehrfachauswahl**:
  * Kann skaliert und rotiert werden (sofern kein TextBoxItem in der Auswahl ist).

---

### 2.4 ImageItem (Bilder)
Bilder verhalten sich strukturell exakt wie TextBoxen und Shapes, nutzen aber bildspezifische Undo-Befehle.
* **Klassen**:
  * [`ImageItem`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_item.py)
  * [`ImageResizeHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py)
  * [`ImageMoveHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py)
  * [`ImageRotateHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py)
  * [`ImageOptionsHandle`](file:///c:/Users/ludwi/.gemini/antigravity/scratch/pdf_annotator/items/image_handles.py)
* **Auswahl (Selection)**:
  * Szene ruft `set_selected_custom(True)` auf.
* **Verschieben**:
  * Über das `ImageMoveHandle` (Pille) oder direktes Ziehen des Bildes.
* **Größenänderung (Resize)**:
  * Über 6 `ImageResizeHandle`s. Skaliert die Breite/Höhe des Bildes.
* **Rotation**:
  * Über `ImageRotateHandle` (unten). Rotiert das Bild um seinen Mittelpunkt.
* **Mehrfachauswahl**:
  * Vollständig unterstützt (sofern keine TextBox dabei ist).

---

## 3. Identifizierte Probleme & Inkonsistenzen (Refactoring-Bedarf)

1. **Redundanter Code**: 
   * Nahezu identische Handle-Erstellungs-, Repositionierungs- und Rendering-Logik ist über `TextBoxItem`, `ShapeItem` und `ImageItem` kopiert.
   * `StrokeItem` und `HighlightItem` kochen mit dem `BoundingBoxHandleManager` ein komplett eigenes Süppchen auf Szenen-Ebene.
2. **Inkonsistente Features**:
   * Einzelne Strokes/Highlighters können nicht rotiert werden, Gruppen aus Strokes aber schon.
   * TextBoxen verhindern das Skalieren von Gruppen komplett, obwohl sie theoretisch im Gruppenverbund skaliert werden könnten (durch Ändern der Box-Dimensionen).
3. **Visuelle Abweichungen**:
   * Die Griffe sehen je nach Item-Typ minimal anders aus oder sind an unterschiedlichen Positionen platziert (z. B. 8 Handles bei Strokes vs. 6 Handles bei Text/Shapes/Images).
4. **Schwierige Wartbarkeit**:
   * Jedes Mal, wenn ein Handle-Design oder Hover-Effekt angepasst wird, müssen mehrere Klassen und separate Handle-Dateien angefasst werden.
