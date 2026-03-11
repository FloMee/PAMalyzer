import pyqtgraph.functions as fn
import pytest
from PyQt5 import QtCore, QtGui

import SupportClasses_GUI


@pytest.fixture
def lighted_file_list(qtbot):
    col_none = QtGui.QColor(255, 0, 0, 100)
    col_posdark = QtGui.QColor(255, 255, 0, 100)
    col_named = QtGui.QColor(0, 255, 0, 100)
    flist = SupportClasses_GUI.LightedFileList(col_none, col_posdark, col_named, None)

    flist.sortRank = True
    flist.showAll = True
    qtbot.addWidget(flist)
    return flist


@pytest.fixture
def sortable_item_empty(qtbot, lighted_file_list):
    lw_item = SupportClasses_GUI.SortableListWidgetItem(lighted_file_list)
    lw_item.setData(QtCore.Qt.UserRole, {})
    return lw_item


@pytest.fixture
def sortable_item_one(qtbot, lighted_file_list):
    lw_item = SupportClasses_GUI.SortableListWidgetItem(lighted_file_list)
    lw_item.setText("1.wav")
    data = {
        "Bartgeier": [57.3, 20.4, 16.2],
        "Haubenlerche": [12.2, 10.1, 12.2],
        "Common Redstart": [93.1],
    }
    lw_item.setData(QtCore.Qt.UserRole, data)
    return lw_item


@pytest.fixture
def sortable_item_two(qtbot, lighted_file_list):
    lw_item = SupportClasses_GUI.SortableListWidgetItem(lighted_file_list)
    lw_item.setText("2.wav")
    data = {"Bartgeier": [88.3, 10.1], "Haubenlerche": [12.2]}
    lw_item.setData(QtCore.Qt.UserRole, data)
    return lw_item


@pytest.fixture
def sortable_item_dirup(qtbot, lighted_file_list):
    lw_item = SupportClasses_GUI.SortableListWidgetItem(lighted_file_list)
    lw_item.setText("../")
    return lw_item


@pytest.fixture
def qicon_vulture_one(qtbot):
    pixmap = QtGui.QPixmap(50, 10)
    blackben = fn.mkPen(
        color=(
            160,
            160,
            160,
            255,
        ),
        width=2,
    )
    painter = QtGui.QPainter(pixmap)
    painter.setPen(blackben)
    painter.drawRect(QtGui.QPixmap(44, 10).rect())
    qtbot.wait(1000)
    painter.end()
    pixmap.fill(QtGui.QColor(255, 255, 0, 0))
    return QtGui.QIcon(pixmap)


def test_lower_than(lighted_file_list, sortable_item_one, sortable_item_two):
    lighted_file_list.currentSpecies = "Bartgeier"
    sortable_item_one.maxConf = sortable_item_one.getConfidenceRange(
        "Bartgeier", (0, 100)
    )[1]
    sortable_item_two.maxConf = sortable_item_two.getConfidenceRange(
        "Bartgeier", (0, 100)
    )[1]

    assert sortable_item_one > sortable_item_two


def test_lower_than_equal_max(lighted_file_list, sortable_item_one, sortable_item_two):
    lighted_file_list.currentSpecies = "Haubenlerche"
    sortable_item_one.maxConf = sortable_item_one.getConfidenceRange(
        "Haubenlerche", (0, 100)
    )[1]
    sortable_item_two.maxConf = sortable_item_two.getConfidenceRange(
        "Haubenlerche", (0, 100)
    )[1]

    assert sortable_item_one < sortable_item_two


def test_lower_than_all_species(
    lighted_file_list, sortable_item_one, sortable_item_two
):
    lighted_file_list.currentSpecies = "Species"
    assert sortable_item_one < sortable_item_two


def test_lower_than_dirup_item(
    lighted_file_list, sortable_item_one, sortable_item_dirup
):
    lighted_file_list.currentSpecies = "Haubenlerche"
    assert sortable_item_one > sortable_item_dirup


def test_min_max_confidence_with_empty_data_empty_species(qtbot, sortable_item_empty):
    assert sortable_item_empty.getConfidenceRange("", (0, 100)) == (-1, 0)


def test_min_max_confidence_with_empty_data_species(qtbot, sortable_item_empty):
    assert sortable_item_empty.getConfidenceRange("Bartgeier", (0, 100)) == (-1, 0)


def test_min_max_confidence_with_data_empty_species(qtbot, sortable_item_one):
    assert sortable_item_one.getConfidenceRange("", (0, 100)) == (-1, 0)


def test_min_max_confidence_with_data_all_species(qtbot, sortable_item_one):
    assert sortable_item_one.getConfidenceRange("Species", (0, 100)) == (10.1, 93.1)


def test_min_max_confidence_with_data_species(qtbot, sortable_item_one):
    assert sortable_item_one.getConfidenceRange("Bartgeier", (0, 100)) == (16.2, 57.3)


# def test_paint_vulture(qtbot, lighted_file_list, sortable_item_one, qicon_vulture_one):
#     lighted_file_list.insertItem(1, sortable_item_one)
#     sortable_item_one.paint((0, 90), "Bartgeier", (0, 24 * 3600))
#     assert not sortable_item_one.isHidden()
#     lighted_file_list.showAll = False
#     sortable_item_one.paint((0, 90), "Bartgeier", (0, 24 * 3600))
#     assert sortable_item_one.isHidden()
#     sortable_item_one.paint((0, 90), "Species", (0, 24 * 3600))
#     assert not sortable_item_one.isHidden()
#     sortable_item_one.paint((0, 10), "non-existent", (0, 24 * 3600))
#     assert sortable_item_one.isHidden()


def test_paint_icon(qtbot, sortable_item_one, lighted_file_list):
    sortable_item_one.paintIcon(True, 50, 50)
    pixmap = sortable_item_one.icon().pixmap(50, 10)
    image = pixmap.toImage()
    assert image.width() == 50
    assert image.height() == 10
    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixel(x, y)
            # print(
            #     "({},{}): {},{},{}".format(
            #         x,
            #         y,
            #         QtGui.QColor(pixel).red(),
            #         QtGui.QColor(pixel).green(),
            #         QtGui.QColor(pixel).blue(),
            #     )
            # )
            if ((y == 0 or y == 9) and x < 24) or x == 0 or x == 24 or x == 25:
                assert QtGui.QColor(pixel).red() == 160
                assert QtGui.QColor(pixel).green() == 160
                assert QtGui.QColor(pixel).blue() == 160
            else:
                assert QtGui.QColor(pixel).red() == 100
                assert QtGui.QColor(pixel).green() == 100
                assert QtGui.QColor(pixel).blue() == 0

    # item without data
    sortable_item_one.paintIcon(False, 50, 50)
    pixmap = sortable_item_one.icon().pixmap(50, 10)
    image = pixmap.toImage()
    assert image.width() == 50
    assert image.height() == 10
    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixel(x, y)
            assert QtGui.QColor(pixel).red() == 0
            assert QtGui.QColor(pixel).green() == 0
            assert QtGui.QColor(pixel).blue() == 0

    # data but not current species
    sortable_item_one.paintIcon(True, -1, 50)
    pixmap = sortable_item_one.icon().pixmap(50, 10)
    image = pixmap.toImage()
    assert image.width() == 50
    assert image.height() == 10

    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixel(x, y)
            if y == 0 or y == 9 or x == 0 or x == 49:
                assert QtGui.QColor(pixel).red() == 160
                assert QtGui.QColor(pixel).green() == 160
                assert QtGui.QColor(pixel).blue() == 160
            else:
                assert QtGui.QColor(pixel).red() == 0
                assert QtGui.QColor(pixel).green() == 0
                assert QtGui.QColor(pixel).blue() == 0

    # Don't know data
    sortable_item_one.paintIcon(True, 0, 50)
    pixmap = sortable_item_one.icon().pixmap(50, 10)
    image = pixmap.toImage()
    assert image.width() == 50
    assert image.height() == 10

    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixel(x, y)
            assert QtGui.QColor(pixel).red() == 100
            assert QtGui.QColor(pixel).green() == 0
            assert QtGui.QColor(pixel).blue() == 0
    # confirmed segments
    sortable_item_one.paintIcon(True, 100, 50)
    pixmap = sortable_item_one.icon().pixmap(50, 10)
    image = pixmap.toImage()
    assert image.width() == 50
    assert image.height() == 10

    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixel(x, y)
            assert QtGui.QColor(pixel).red() == 0
            assert QtGui.QColor(pixel).green() == 100
            assert QtGui.QColor(pixel).blue() == 0
