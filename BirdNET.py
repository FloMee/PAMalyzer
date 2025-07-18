# BirdNET.py
# Interface and algorithms for the BirdNET classifiers - taken and adapted
# from Stefan Kahl
# BirdNET-Lite: https://github.com/kahst/BirdNET-Lite
# BirdNET-Analyzer: https://github.com/kahst/BirdNET-Analyzer

# Version 3.2-BirdNET 21/03/2024
# Authors: Stephen Marsland, Nirosha Priyadarshani, Julius Juodakis, Virginia Listanti, Florian Meerheim

#    AviaNZ bioacoustic analysis program
#    Copyright (C) 2017--2024

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

#    Note that the BirdNET models are licensed under: CC-BY-NC-SA 4.0
#    see https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en

# import statements for BirdNET-Lite

import copy
import math
import operator
import os
import pathlib
import time
import traceback

import librosa
import numpy as np
from PyQt5.QtCore import QDir, QObject, QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tensorflow import lite as tflite
from tqdm import tqdm

import Segment

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["CUDA_VISIBLE_DEVICES"] = ""


class BirdNETDialog(QDialog):
    def __init__(self, parent=None):
        super(BirdNETDialog, self).__init__(parent)
        self.parent = parent

        self.slist_path = ""
        self.classifierPath = ""
        self.setWindowTitle("Classify Recordings with BirdNET")
        self.setWindowIcon(QIcon("img/PAMalyzer.ico"))

        self.setWindowFlags(
            (self.windowFlags() ^ Qt.WindowContextHelpButtonHint)
            | Qt.WindowCloseButtonHint
        )

        lbltitle = QLabel(
            "To analyze the audiofiles of the current directory, "
            "set the parameters for BirdNET-Lite or BirdNET-Analyzer. Be aware "
            "that the process might take several hours, depending on the number of "
            "files, calculation power and number of threads."
        )
        lbltitle.setWordWrap(True)

        # BirdNET-Lite/BirdNET-Analyzer options
        self.lite = QRadioButton("BirdNET-Lite")
        self.analyzer = QRadioButton("BirdNET-Analyzer")
        self.lite.clicked.connect(self.updateDialog)
        self.analyzer.clicked.connect(self.updateDialog)

        self.lat_label = QLabel("Latitude")
        self.lat_label.setToolTip(
            "Recording location latitude; Values in [-90; 90]; Defaults to -1.00."
        )
        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lat.setValue(-1.0)
        self.lat.valueChanged.connect(self.updateDialog)

        self.lon_label = QLabel("Longitude")
        self.lon_label.setToolTip(
            "Recording location longitude; Values in [-180; 180]; Defaults to -1.00."
        )
        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180, 180)
        self.lon.setValue(-1.0)
        self.lon.valueChanged.connect(self.updateDialog)

        self.week_label = QLabel("Week")
        self.week_label.setToolTip(
            "Week of the recording; Values in [0; 48]; "
            "Divide year into 48 weeks — 4 weeks per month; Defaults to 0."
        )
        self.week = QSpinBox()
        self.week.setRange(0, 48)
        self.week.valueChanged.connect(self.updateDialog)

        self.overlap_label = QLabel("Overlap")
        self.overlap_label.setToolTip(
            "BirdNET cuts your recordings into "
            "chunks of 3 s lenght internally; Overlap defines the number of "
            "seconds the single segments overlap; Values in [0.0; 2.9]; Defaults "
            "to 0.0."
        )
        self.overlap = QDoubleSpinBox()
        self.overlap.setRange(0, 2.9)
        self.overlap.setSingleStep(0.1)
        self.overlap.setValue(0.0)

        self.sensitivity_label = QLabel("Sensitivity")
        self.sensitivity_label.setToolTip(
            "Detection sensitivity; Higher "
            "values result in higher sensitivity; Values in [0.5, 1.5]; Defaults "
            "to 1.0."
        )
        self.sensitivity = QDoubleSpinBox()
        self.sensitivity.setRange(0.5, 1.5)
        self.sensitivity.setSingleStep(0.05)
        self.sensitivity.setValue(1.0)

        self.min_conf_label = QLabel("Minimum confidence")
        self.min_conf_label.setToolTip(
            "Minimum confidence value in the output; "
            "Values in [0.01;0.99]; Defaults to 0.1."
        )
        self.min_conf = QDoubleSpinBox()
        self.min_conf.setRange(0.01, 0.99)
        self.min_conf.setSingleStep(0.01)
        self.min_conf.setValue(0.1)

        self.slist = QLineEdit()
        self.slist.setReadOnly(True)
        self.slist.setClearButtonEnabled(True)
        self.slist.findChild(QToolButton).setEnabled(True)
        self.slist.textChanged.connect(self.updateDialog)

        self.btn_slist = QPushButton("Select custom species list")
        self.btn_slist.setToolTip(
            "A “white list” that includes the species of "
            "interest; Must be a subset of the original species-lists of "
            "BirdNET-Lite or BirdNET-Analyzer respectively and in the selected "
            "language; Find these files in the installation directory of PAMalyzer "
            "under labels."
        )
        self.btn_slist.clicked.connect(self.chooseSpeciesList)

        self.threads_label = QLabel("Number of threads")
        self.threads_label.setToolTip(
            "Number of threads used for calculation; "
            "Defaults to the number of available cores of the CPU."
        )
        self.threads = QSpinBox()
        self.threads.setRange(1, os.cpu_count())
        self.threads.setValue(os.cpu_count())

        self.mea = QCheckBox("Calculate moving exponential average")
        self.mea.setToolTip(
            "If set, the original confidence values are "
            "smoothed and pooled with a moving mean exponential average with a "
            "width of 3 chunks; Used to potentially remove some false positives."
        )
        self.datetime_format_label = QLabel("Datetime format")
        self.datetime_format = QLineEdit()
        self.datetime_format.textChanged.connect(self.updateDialog)

        self.locale = QComboBox()
        # TODO: get list of possible languages from labels_directory?
        self.locale.addItems(
            [
                "af",
                "ar",
                "cs",
                "da",
                "de",
                "en",
                "es",
                "fi",
                "fr",
                "hu",
                "it",
                "ja",
                "ko",
                "nl",
                "no",
                "pl",
                "pt",
                "ro",
                "ru",
                "sk",
                "sl",
                "sv",
                "th",
                "tr",
                "uk",
                "zh",
            ]
        )
        self.locale.setCurrentIndex(5)

        # Analyzer specific options

        self.batchsize_label = QLabel("Batchsize")
        self.batchsize_label.setToolTip(
            "Number of chunks that are analysed "
            "concurrently; May influence the processing time but not the output; "
            "Defaults to 1."
        )
        self.batchsize = QSpinBox()
        self.batchsize.setValue(1)

        self.sf_thresh_label = QLabel("Threshold for location filter")
        self.sf_thresh_label.setToolTip(
            "If Latitude, Longitude and Week are "
            "set BirdNET-Analyzer calculates a custom species list; Species with a "
            "calculated value below this threshold are not included in the output "
            "list; Defaults to: 0,03."
        )
        self.sf_thresh = QDoubleSpinBox()
        self.sf_thresh.setRange(0.000001, 0.999999)
        self.sf_thresh.setSingleStep(0.000001)
        self.sf_thresh.setValue(0.030000)
        self.sf_thresh.setDecimals(6)
        self.sf_thresh.setDisabled(True)

        self.customClassifier = QLineEdit()
        self.customClassifier.setReadOnly(True)
        self.customClassifier.setClearButtonEnabled(True)
        self.customClassifier.findChild(QToolButton).setEnabled(True)
        self.customClassifier.textChanged.connect(self.updateDialog)

        self.btn_customClassifier = QPushButton("Select custom classifier")
        self.btn_customClassifier.setToolTip(
            "Select the classifier that is used by BirdNET-Analyzer. "
            "This can be either one of the classifiers that are shipped with "
            "BirdNET or a self trained custom classifier based on BirdNET-Analyzer"
        )
        self.btn_customClassifier.clicked.connect(self.chooseCustomClassifier)

        self.btnAdvanced = QPushButton("Show Advanced Settings")
        self.btnAdvanced.clicked.connect(self.updateSettings)

        # Button to start analysis
        self.btnAnalyze = QPushButton("Analyze")
        self.btnAnalyze.clicked.connect(self.onClickanalyze)

        # labels for QLineEdit analyze options

        # parameter layout
        self.basic = QGroupBox()
        self.advanced = QGroupBox()
        self.analyze = QGroupBox()

        analyze_layout = QHBoxLayout()

        param_basic = QGridLayout()
        param_advanced = QGridLayout()

        param_basic.addWidget(self.lite, 0, 0)
        param_basic.addWidget(self.analyzer, 1, 0)

        param_basic.addWidget(self.lat_label, 2, 0)
        param_basic.addWidget(self.lat, 2, 1)

        param_basic.addWidget(self.lon_label, 3, 0)
        param_basic.addWidget(self.lon, 3, 1)

        param_basic.addWidget(self.week_label, 4, 0)
        param_basic.addWidget(self.week, 4, 1)

        param_advanced.addWidget(self.overlap_label, 5, 0)
        param_advanced.addWidget(self.overlap, 5, 1)

        param_advanced.addWidget(self.sensitivity_label, 6, 0)
        param_advanced.addWidget(self.sensitivity, 6, 1)

        param_advanced.addWidget(self.min_conf_label, 7, 0)
        param_advanced.addWidget(self.min_conf, 7, 1)

        param_basic.addWidget(self.slist, 8, 0)
        param_basic.addWidget(self.btn_slist, 8, 1)

        param_advanced.addWidget(self.threads_label, 9, 0)
        param_advanced.addWidget(self.threads, 9, 1)

        param_advanced.addWidget(self.mea, 10, 1)

        param_advanced.addWidget(self.datetime_format_label, 11, 0)
        param_advanced.addWidget(self.datetime_format, 11, 1)

        param_basic.addWidget(QLabel("Language of the labels"), 12, 0)
        param_basic.addWidget(self.locale, 12, 1)

        param_advanced.addWidget(self.batchsize_label, 13, 0)
        param_advanced.addWidget(self.batchsize, 13, 1)

        param_advanced.addWidget(self.sf_thresh_label, 14, 0)
        param_advanced.addWidget(self.sf_thresh, 14, 1)

        param_advanced.addWidget(self.customClassifier, 15, 0)
        param_advanced.addWidget(self.btn_customClassifier, 15, 1)

        param_basic.addWidget(self.btnAdvanced, 14, 1)
        analyze_layout.addWidget(self.btnAnalyze)

        # overall Layout
        layout = QVBoxLayout()
        layout.addWidget(lbltitle)
        self.basic.setLayout(param_basic)
        self.advanced.setLayout(param_advanced)
        self.analyze.setLayout(analyze_layout)
        layout.addWidget(self.basic)
        layout.addWidget(self.advanced)
        layout.addWidget(self.analyze)
        layout.setSpacing(25)
        self.setLayout(layout)

        # default: BirdNET-Lite
        self.lite.setChecked(True)
        self.advanced.hide()
        self.min_size = self.size()
        self.updateDialog()

    def updateSettings(self):
        if self.btnAdvanced.text() == "Show Advanced Settings":
            self.advanced.show()
            self.btnAdvanced.setText("Hide Advanced Settings")
        else:
            self.advanced.hide()
            self.btnAdvanced.setText("Show Advanced Settings")

        self.adjustSize()

    def chooseSpeciesList(self):
        species_list = QFileDialog.getOpenFileName(
            self, "Choose filter species list", filter="Text (*.txt)"
        )
        self.slist.setText(os.path.basename(species_list[0]))
        self.slist_path = species_list[0]
        # self.updateDialog()

    def chooseCustomClassifier(self):
        customClassifier = QFileDialog.getOpenFileName(
            self, "Choose BirdNET-Analyzer model", filter="Model (*.tflite)"
        )
        self.customClassifier.setText(os.path.basename(customClassifier[0]))
        self.classifierPath = customClassifier[0]

    def validateInputParameters(self):
        correct = True
        for param in [self.lat, self.lon, self.week]:
            if not param.hasAcceptableInput() and param.text() != "":
                correct = False
                param.setStyleSheet("background-color: red")
            else:
                param.setStyleSheet("background-color: white")
        for param in [
            self.overlap,
            self.sensitivity,
            self.min_conf,
            self.threads,
            self.sf_thresh,
            self.batchsize,
        ]:
            if not param.hasAcceptableInput():
                correct = False
                param.setStyleSheet("background-color: red")
            else:
                param.setStyleSheet("background-color: white")
        return correct

    def onClickanalyze(self):
        if self.validateInputParameters():
            param_dict = {
                "lite": self.lite.isChecked(),
                "lat": self.lat.value(),
                "lon": self.lon.value(),
                "week": self.week.value() if self.week.value() > 0 else -1,
                "overlap": self.overlap.value(),
                "sensitivity": (1 - (self.sensitivity.value() - 1)),
                "min_conf": self.min_conf.value(),
                "slist": self.slist_path,
                "threads": self.threads.value(),
                "mea": self.mea.isChecked(),
                "datetime_format": self.datetime_format.text(),
                "locale": self.locale.currentText(),
                "batchsize": self.batchsize.value(),
                "sf_thresh": self.sf_thresh.value(),
                "classifier": self.classifierPath if self.classifierPath else None,
            }

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Non-Commercial Licence!")
            msg.setInformativeText(
                "The model of {} is licenced under a "
                "Attribution-NonCommercial-ShareAlike 4.0 "
                "International Licence.\n\nYou accept the "
                "licence by analysing your files.".format(
                    "BirdNET-Lite" if self.lite.isChecked() else "BirdNET-Analyzer"
                )
            )
            msg.setWindowTitle("Consent required")
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            response = msg.exec_()
            if response == QMessageBox.Ok:
                self.parent.BirdNET = BirdNET(self.parent)
                birdnet = self.parent.BirdNET
                setattr(birdnet, "param", param_dict)
                self.parent.BirdNET.main()

            self.close()
            # if self.parent.BirdNET.threadpool.waitForDone():
            #     self.parent.loadFile(name=self.parent.filename)
            #     self.parent.fillFileList(self.parent.SoundFileDir, os.path.basename(self.parent.filename))

        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Parameters!")
            msg.setInformativeText(
                "You did not input correct values for "
                "parameters, please check the red parameters again!"
            )
            msg.setWindowTitle("Warning")
            msg.exec_()

    def updateDialog(self):
        print("Update Dialog")
        if self.lite.isChecked():
            self.datetime_format.setVisible(False)
            self.datetime_format_label.setVisible(False)
            self.batchsize.setVisible(False)
            self.batchsize_label.setVisible(False)
            self.sf_thresh.setVisible(False)
            self.sf_thresh_label.setVisible(False)
            self.lat.setDisabled(False)
            self.lon.setDisabled(False)
            self.week.setDisabled(False)
            self.btn_slist.setDisabled(False)
            self.customClassifier.setVisible(False)
            self.btn_customClassifier.setVisible(False)
            if self.datetime_format.text() != "":
                self.week.setDisabled(True)
            elif self.week.value() != 0:
                self.datetime_format.setDisabled(True)
            else:
                self.datetime_format.setDisabled(False)
                self.week.setDisabled(False)

        else:
            self.mea.setChecked(False)
            self.datetime_format.setVisible(False)
            self.datetime_format_label.setVisible(False)
            self.batchsize.setVisible(True)
            self.batchsize_label.setVisible(True)
            self.sf_thresh.setVisible(True)
            self.sf_thresh_label.setVisible(True)
            self.customClassifier.setVisible(True)
            self.btn_customClassifier.setVisible(True)
            if self.lat.value() != -1 or self.lon.value() != -1:
                self.slist.clear()
                self.btn_slist.setDisabled(True)
                self.sf_thresh.setDisabled(False)
                self.week.setDisabled(False)
            elif self.slist.text() != "":
                self.lat.setDisabled(True)
                self.lon.setDisabled(True)
                self.week.sitDisabled(True)
                self.sf_thresh.setDisabled(True)
            else:
                self.lat.setDisabled(False)
                self.lon.setDisabled(False)
                self.week.setDisabled(False)
                self.sf_thresh.setDisabled(True)
                self.week.setDisabled(True)
                self.btn_slist.setDisabled(False)
                # self.slist.setText(self.slist_path)

        self.adjustSize()


class BirdNET(QWidget):
    def __init__(self, AviaNZmanual):
        super(BirdNET, self).__init__()
        self.AviaNZ = AviaNZmanual
        self.filelist = []
        self.fillFileList(AviaNZmanual.listFiles.listOfFiles)
        self.param = None
        self.progress = QProgressDialog()
        self.progress.setCancelButton(None)
        self.progress.setWindowTitle("PAMalyzer")
        self.progress.setWindowIcon(QIcon("img/PAMalyzer.ico"))
        self.progress.setAutoClose(True)
        self.progress.setRange(0, len(self.filelist))
        self.threadpool = QThreadPool()
        self.workers_done = 0

    def fillFileList(self, filelist):
        for file in filelist:
            if file.isFile():
                self.filelist.append(str(pathlib.PurePath(file.absoluteFilePath())))
            if file.fileName() == "..":
                continue
            elif file.isDir():
                self.fillFileList(
                    QDir(file.absoluteFilePath()).entryInfoList(
                        ["*.wav"],
                        filters=QDir.AllDirs | QDir.NoDot | QDir.Files,
                        sort=QDir.DirsFirst,
                    )
                )

    def loadLabels(self):
        # Load labels
        if self.param["lite"]:
            lblpath = os.path.join(
                "labels", "Lite", "labels_{}.txt".format(self.param["locale"])
            )
        elif self.param["classifier"]:
            lblpath = lblpath = (
                self.param["classifier"].rpartition(".")[0] + "_Labels.txt"
            )
        else:
            lblpath = os.path.join(
                "labels",
                "Analyzer",
                "BirdNET_GLOBAL_6K_V2.4_Labels_{}.txt".format(self.param["locale"]),
            )

        with open(lblpath, "r", encoding="utf8") as lfile:
            classes = [line[:-1] for line in lfile]

        return classes

    @pyqtSlot()
    def updateProgress(self):
        self.progress.setValue(self.progress.value() + 1)
        self.progress.setLabelText(
            "Analyzing files... {}/{} done".format(
                self.progress.value(), len(self.filelist)
            )
        )

    @pyqtSlot(list)
    def updateFilelist(self, filelist):
        self.workers_done += 1
        if self.workers_done == self.total_workers:
            self.AviaNZ.database.commit()
            self.AviaNZ.loadFile(name=self.AviaNZ.filename)
            self.AviaNZ.fillFileList(
                self.AviaNZ.SoundFileDir, os.path.basename(self.AviaNZ.filename)
            )
            end_time = time.time()
            print(
                "\nAnalysis sucessfully completed in {:.0f}h {:.0f}min {:.0f}s".format(
                    (end_time - self.start_time) // 3600,
                    (end_time - self.start_time) // 60,
                    (end_time - self.start_time) % 60,
                )
            )

    @pyqtSlot(Segment.SegmentList, str)
    def updateDatabase(self, segList, filename):
        segList.parent = self.AviaNZ
        segList.save_to_database(filename)

    def main(self):
        try:
            self.labels = self.loadLabels()

            # create list of lists of filenames to pass to different threads
            step = -(-len(self.filelist) // self.param["threads"])
            file_threads = [
                self.filelist[i : i + step] for i in range(0, len(self.filelist), step)
            ]
            self.progress.setValue(0)
            self.progress.setLabelText(
                "Analyzing {} files...".format(len(self.filelist))
            )
            self.progress.show()
            self.start_time = time.time()
            self.total_workers = len(file_threads)
            for i, flist in enumerate(file_threads):
                worker = BirdNET_Worker(
                    self, param=self.param, wid=i, filelist=flist, labels=self.labels
                )
                worker.fileProcessed.update.connect(self.updateProgress)
                worker.filelistProcessed.done.connect(self.updateFilelist)
                worker.sendSegList.send.connect(self.AviaNZ.database.insert_segments)
                self.threadpool.start(worker)

        except:
            print(traceback.format_exc())


class MyEmitter(QObject):
    send = pyqtSignal(Segment.SegmentList, str)
    done = pyqtSignal(list)
    update = pyqtSignal()


class BirdNET_Worker(QRunnable):
    def __init__(self, parent, param, wid, filelist, labels, *args, **kwargs):
        super(BirdNET_Worker, self).__init__()
        self.parent = parent
        self.wid = wid
        self.filelist = filelist
        self.m_interpreter = None
        self.model = None
        self.lite = param["lite"]
        self.lat = param["lat"]
        self.lon = param["lon"]
        self.week = param["week"]
        self.overlap = param["overlap"]
        self.sensitivity = param["sensitivity"]
        self.min_conf = param["min_conf"]
        self.sf_thresh = param["sf_thresh"]
        self.locale = param["locale"]
        self.slist = param["slist"]
        self.threads = param["threads"]
        self.mea = param["mea"]
        self.datetime_format = param["datetime_format"]
        self.batchsize = param["batchsize"]
        self.classifier = param["classifier"]
        self.labels = labels
        self.fileProcessed = MyEmitter()
        self.filelistProcessed = MyEmitter()
        self.sendSegList = MyEmitter()
        self.initProcess()

    def run(self, *args, **kwargs):
        self.parent.progress.activateWindow()
        with tqdm(
            total=len(self.filelist),
            desc="Thread: {}".format(self.wid),
            position=self.wid,
            leave=True,
        ) as pbar:
            for file in self.filelist:
                pbar.set_postfix(file=os.path.basename(file))
                self.analyze(file)
                pbar.update(1)
        pbar.close()
        self.filelistProcessed.done.emit(self.filelist)

    def loadModel(self):
        try:
            if self.lite:
                mdlpath = os.path.join(
                    "models", "Lite", "BirdNET_6K_GLOBAL_MODEL.tflite"
                )
            elif self.classifier:
                mdlpath = self.classifier
            else:
                mdlpath = os.path.join(
                    "models", "Analyzer", "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite"
                )
            # Load TFLite model and allocate tensors.
            interpreter = tflite.Interpreter(model_path=mdlpath)
            interpreter.allocate_tensors()
            # Get input and output tensors.
            input_details = interpreter.get_input_details()
            output_details = interpreter.get_output_details()

            # Get input tensor index
            input_layer_index = input_details[0]["index"]
            if self.lite:
                mdata_input_index = input_details[1]["index"]
            else:
                mdata_input_index = None
            output_layer_index = output_details[0]["index"]

            # TODO: check if self.labels works or if deepcopy is needed
            model = [
                input_layer_index,
                mdata_input_index,
                output_layer_index,
                copy.deepcopy(self.labels),
                interpreter,
            ]

        except Exception():
            print(traceback.format_exc())

        return model

    def loadMetaModel(self):
        # Load TFLite model and allocate tensors.
        self.m_interpreter = tflite.Interpreter(
            model_path=os.path.join(
                "models", "Analyzer", "BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16.tflite"
            )
        )
        self.m_interpreter.allocate_tensors()

        # Get input and output tensors.
        input_details = self.m_interpreter.get_input_details()
        output_details = self.m_interpreter.get_output_details()

        # Get input tensor index
        self.m_intput_layer_index = input_details[0]["index"]
        self.m_output_layer_index = output_details[0]["index"]

    def getSpeciesList(self, path):
        if self.lite:
            slist = self.loadCustomSpeciesList(path)
        elif self.lat == -1 and self.lon == -1:
            slist = self.loadCustomSpeciesList(path)
        else:
            slist = self.predictSpeciesList()
        return slist

    def loadCustomSpeciesList(self, path):
        slist = []
        if path:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf8") as csfile:
                    for line in csfile.readlines():
                        slist.append(line.replace("\r", "").replace("\n", ""))
            else:
                raise Exception("Custom species list file or file path does not exist!")
        return slist

    def predictSpeciesList(self):
        l_filter = self.explore()
        # cfg.SPECIES_LIST_FILE = None
        slist = []
        for s in l_filter:
            if s[0] >= self.sf_thresh:
                slist.append(s[1])

        return slist

    def explore(self):
        # Make filter prediction
        l_filter = self.predictFilter()

        # Apply threshold
        l_filter = np.where(l_filter >= self.sf_thresh, l_filter, 0)

        # Zip with labels
        l_filter = list(zip(l_filter, self.labels))

        # Sort by filter value
        l_filter = sorted(l_filter, key=lambda x: x[0], reverse=True)

        return l_filter

    def predictFilter(self):
        # Does interpreter exist?
        if self.m_interpreter is None:
            self.loadMetaModel()

        # Prepare mdata as sample
        sample = np.expand_dims(
            np.array([self.lat, self.lon, self.week], dtype="float32"), 0
        )

        # Run inference
        self.m_interpreter.set_tensor(self.m_intput_layer_index, sample)
        self.m_interpreter.invoke()

        return self.m_interpreter.get_tensor(self.m_output_layer_index)[0]

    def splitSignal(self, sig, rate, seconds=3.0, minlen=1.5):
        # Split signal with overlap
        sig_splits = []
        for i in range(0, len(sig), int((seconds - self.overlap) * rate)):
            split = sig[i : i + int(seconds * rate)]

            # End of signal?
            if len(split) < int(minlen * rate):
                break

            # Signal chunk too short? Fill with zeros (Lite) or noise (Analyzer).
            if len(split) < int(rate * seconds):
                if self.lite:
                    temp = np.zeros((int(rate * seconds)))
                    temp[: len(split)] = split
                    split = temp
                else:
                    split = np.hstack(
                        (
                            split,
                            self.noise(split, (int(rate * seconds) - len(split)), 0.5),
                        )
                    )

            sig_splits.append(split)

        return sig_splits

    def noise(self, sig, shape, amount=None):
        random_seed = 42
        random = np.random.RandomState(random_seed)

        # Random noise intensity
        if amount is None:
            amount = random.uniform(0.1, 0.5)

        # Create Gaussian noise
        try:
            noise = random.normal(min(sig) * amount, max(sig) * amount, shape)
        except:
            noise = np.zeros(shape)

        return noise.astype("float32")

    def readAudioData(self, path, sample_rate=48000):
        # TODO: Does the following makes sense? Taken from BirdNET-Analyzer
        try:
            sig, rate = librosa.load(
                path, sr=sample_rate, mono=True, res_type="kaiser_fast"
            )
        except:
            print(traceback.format_exc())
            sig, rate = [], sample_rate

        # Split audio into 3-second chunks
        chunks = self.splitSignal(sig, rate)

        return chunks

    def convertMetadata(self, filename):
        if self.datetime_format:
            day = time.strptime(os.path.split(filename)[1], self.datetime_format)[7]
            week = math.cos(math.radians(day / 365 * 360)) + 1

        else:
            # Convert week to cosine
            if self.week >= 1 and self.week <= 48:
                week = math.cos(math.radians(self.week * 7.5)) + 1
            else:
                week = -1

        # Add binary mask
        mask = np.ones((3,))
        if self.lat == -1 or self.lon == -1:
            mask = np.zeros((3,))
        if week == -1:
            mask[2] = 0.0

        return np.concatenate([np.array([self.lat, self.lon, week]), mask])

    def custom_sigmoid(self, x):
        return 1 / (1.0 + np.exp(-self.sensitivity * x))

    def flat_sigmoid(self, x, sensitivity=-1):
        return 1 / (1.0 + np.exp(sensitivity * np.clip(x, -15, 15)))

    def predict(self, samples):
        interpreter = self.model[4]
        input_layer_index = self.model[0]
        mdata_input_index = self.model[1]
        output_layer_index = self.model[2]
        # labels = model[3]

        if self.lite:
            # Make a prediction
            interpreter.set_tensor(
                input_layer_index, np.array(samples[0], dtype="float32")
            )
            interpreter.set_tensor(
                mdata_input_index, np.array(samples[1], dtype="float32")
            )
            interpreter.invoke()
            prediction = interpreter.get_tensor(output_layer_index)[0]

            # Apply custom sigmoid

            p_sigmoid = self.custom_sigmoid(prediction)

        else:
            # Prepare sample and pass through model
            data = np.array(samples, dtype="float32")

            # Reshape input tensor
            interpreter.resize_tensor_input(
                input_layer_index, [len(data), *data[0].shape]
            )
            interpreter.allocate_tensors()

            # Make a prediction (Audio only for now)
            interpreter.set_tensor(input_layer_index, np.array(data, dtype="float32"))
            interpreter.invoke()
            prediction = interpreter.get_tensor(output_layer_index)

            p_sigmoid = self.flat_sigmoid(
                np.array(prediction), sensitivity=-self.sensitivity
            )

        return p_sigmoid

    def analyzeAudioData(self, chunks, file):
        # different format for standard and post-processing (mea) approach
        detections = {}
        detections_mea = np.zeros(shape=(len(chunks), len(self.model[3])))

        start = time.time()
        # Parse every chunk
        timestamps = []
        pred_start = 0.0
        sig_length = 3.0

        labels = self.model[3]

        j = 0
        if self.lite:
            # Convert and prepare metadata
            mdata = self.convertMetadata(file)
            mdata = np.expand_dims(mdata, 0)
            for c in chunks:
                # Prepare as input signal
                sig = np.expand_dims(c, 0)

                # Make prediction
                # p1, p2 = self.predict([sig, mdata], model)

                p_sigmoid = self.predict([sig, mdata])

                # Get label and scores for pooled predictions
                p_labels = dict(zip(labels, p_sigmoid))

                # Sort by score
                p_sorted = sorted(
                    p_labels.items(), key=operator.itemgetter(1), reverse=True
                )

                # Remove species that are on blacklist
                for i in range(min(10, len(p_sorted))):
                    if p_sorted[i][0] in [
                        "Human_Human",
                        "Non-bird_Non-bird",
                        "Noise_Noise",
                    ]:
                        p_sorted[i] = (p_sorted[i][0], 0.0)

                # Save result and timestamp
                detections_mea[j] = p_sigmoid
                timestamps.append(pred_start)

                pred_end = pred_start + sig_length
                detections[file + "," + str(pred_start) + "," + str(pred_end)] = (
                    p_sorted[:10]
                )
                pred_start = pred_end - self.overlap
                j += 1

            return (detections_mea.transpose(), timestamps, detections)

        else:
            timestamps_return = []
            start, end = 0, sig_length
            samples = []
            for c in range(len(chunks)):
                # Add to batch
                samples.append(chunks[c])
                timestamps.append([start, end])

                # Advance start and end
                start += sig_length - self.overlap
                end = start + sig_length

                # Check if batch is full or last chunk
                if len(samples) < self.batchsize and c < len(chunks) - 1:
                    continue

                # Predict
                p = self.predict(samples)

                # Add to results
                for i in range(len(samples)):
                    # Get timestamp
                    s_start, s_end = timestamps[i]

                    # Get prediction
                    pred = p[i]

                    # Add to moving exponential average
                    detections_mea[i] = pred
                    timestamps_return.append(s_start)

                    # Assign scores to labels
                    p_labels = dict(zip(labels, pred))

                    # Sort by score
                    p_sorted = sorted(
                        p_labels.items(), key=operator.itemgetter(1), reverse=True
                    )

                    # Store top 5 results and advance indicies
                    detections[file + "," + str(s_start) + "," + str(s_end)] = p_sorted

                # Clear batch
                samples = []
                timestamps = []

            return (detections_mea.transpose(), timestamps_return, detections)

    def convert_mea_output(self, mea_output, file, timestamps):
        detections = {}
        cntr = 0
        for start in timestamps:
            key = "{},{},{}".format(file, start, start + 3)
            detections[key] = [(d, mea_output[d][cntr]) for d in mea_output]
            cntr += 1

        return detections

    def writeAvianzOutput(self, detections, file, white_list):
        """Write detections to Segments, write Segments to SegmentList, save
        SegmentList.
        """
        seg_list = Segment.SegmentList()

        # TODO: get Duration from file

        seg_list.metadata = {
            "Operator": self.parent.AviaNZ.operator,
            "Reviewer": self.parent.AviaNZ.reviewer,
            "Duration": 60,
        }

        for d in detections:
            save = True
            seg = seg_list.getSegment(
                [float(d.split(",")[1]), float(d.split(",")[2]), 0.0, 0.0, []]
            )
            if len(seg[4]) > 0:
                save = False
            for entry in detections[d]:
                if entry[1] >= self.min_conf and (
                    entry[0] in white_list or len(white_list) == 0
                ):
                    seg.addLabel(
                        entry[0].split("_")[1].split(".")[0],
                        float(entry[1]) * 100,
                        filter="BirdNET-Lite" if self.lite else "BirdNET-Analyzer",
                        calltype=entry[0].split("_")[1].split(".")[1]
                        if len(entry[0].split("_")[1].split(".")) > 1
                        else "non-specified",
                    )
            if len(seg[4]) > 0 and save:
                seg_list.addSegment(seg)

        self.sendSegList.send.emit(seg_list, file)

    def movingExpAverage(self, timetable, n=3):
        """Calculate moving exponential average over 3 Segments per Default."""

        weights = np.exp(np.linspace(-1.0, 0.0, n))
        weights /= weights.sum()
        i = 0
        for row in timetable:
            # a = np.convolve(row, weights, mode='full')[:len(row)]
            a = np.convolve(row, weights, mode="full")[n - 1 :]
            # a[:n-1] = row[:n-1]
            # a[:n-1] = a[n-1]
            timetable[i] = a
            i += 1
        return timetable

    def whiteListing(self, timetable, white_list):
        detections = {}
        i = 0
        for j in timetable:
            if (self.model[3][i] in white_list) or (
                len(white_list) == 0
                and self.model[3][i]
                not in ["Human_Human", "Non-bird_Non-bird", "Noise_Noise"]
            ):
                detections[self.model[3][i]] = j
            i += 1
        return detections

    def analyze(self, file):
        try:
            white_list = self.slist

            # Read audio data
            audioData = self.readAudioData(file)

            #     # If no chunks, show error and skip
            #     if len(audioData) == 0:
            #         msg = 'Error: Cannot open audio file {}'.format(fpath)
            #         print(msg, flush=True)
            #         writeErrorLog(msg)
            #         return False

            # Process audio data and get detections
            pp_det, timestamps, def_det = self.analyzeAudioData(audioData, file)

            if self.mea is False:
                self.writeAvianzOutput(def_det, file, white_list)

            elif self.mea is True:
                # apply moving exponential average to pp_det and write results to tempfile
                mea_det = self.whiteListing(self.movingExpAverage(pp_det), white_list)
                mea_det_convert = self.convert_mea_output(mea_det, file, timestamps)
                self.writeAvianzOutput(mea_det_convert, file, white_list)

            self.fileProcessed.update.emit()
        except:
            print(traceback.format_exc())

    def initProcess(self):
        self.model = self.loadModel()
        self.slist = self.getSpeciesList(self.slist)
