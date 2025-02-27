# Version 3.2-BirdNET 21/03/2024
# Authors: Stephen Marsland, Nirosha Priyadarshani, Julius Juodakis, Virginia Listanti, Florian Meerheim

# This is the script that starts AviaNZ. It processes command line options
# and then calls either part of the GUI, or runs on the command line directly.

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

import click
import sys

# Command line running to run a filter is something like
# python AviaNZ.py -c -b -d "/home/marslast/Projects/AviaNZ/Sound Files/train5" -r "Morepork" -w

# For training
# python AviaNZ.py -c -t -d "/home/marslast/Projects/AviaNZ/Sound Files/train5" -e "/home/marslast/Projects/AviaNZ/Sound Files/train6" -r "Morepork" -x 2


# For testing
# python AviaNZ.py -c -u -d "/home/marslast/Projects/AviaNZ/Sound Files/test1" -r "Kiwi (Tokoeka Rakiura)"
@click.command()
@click.option("-c", "--cli", is_flag=True, help="Run in command-line mode")
@click.option("-s", "--cheatsheet", is_flag=True, help="Make the cheatsheet images")
@click.option(
    "-z", "--zooniverse", is_flag=True, help="Make the Zooniverse images and sounds"
)
@click.option(
    "-f", "--infile", type=click.Path(), help="Input wav file (mandatory in CLI mode)"
)
@click.option(
    "-o",
    "--imagefile",
    type=click.Path(),
    help="If specified, a spectrogram will be saved to this file",
)
@click.argument("command", nargs=-1)
def mainlauncher(
    cli,
    cheatsheet,
    zooniverse,
    infile,
    imagefile,
    command,
):
    # adapt path to allow this to be launched from wherever
    import sys, os

    if getattr(sys, "frozen", False):
        appdir = sys._MEIPASS
    else:
        appdir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(appdir)

    # print("Using python at", sys.path)
    # print(os.environ)
    # print("Version", sys.version)

    try:
        import platform, json, shutil
        from jsonschema import validate
        import SupportClasses
    except Exception as e:
        print("ERROR: could not import packages")
        raise

    # determine location of config file and bird lists
    if platform.system() == "Windows":
        # Win
        configdir = os.path.expandvars(os.path.join("%APPDATA%", "PAMalyzer"))
    elif platform.system() == "Linux" or platform.system() == "Darwin":
        # Unix
        configdir = os.path.expanduser("~/.PAMalyzer/")
    else:
        print("ERROR: what OS is this? %s" % platform.system())
        raise

    # if config and bird files not found, copy from distributed backups.
    # so these files will always exist on load (although they could be corrupt)
    # (exceptions here not handled and should always result in crashes)
    if not os.path.isdir(configdir):
        print("Creating config dir %s" % configdir)
        try:
            os.makedirs(configdir)
        except Exception as e:
            print("ERROR: failed to make config dir")
            print(e)
            raise

    # pre-run check of config file validity
    confloader = SupportClasses.ConfigLoader()
    configschema = json.load(open("Config/config.schema"))
    try:
        config = confloader.config(os.path.join(configdir, "AviaNZconfig.txt"))
        validate(instance=config, schema=configschema)
        print("successfully validated config file")
    except Exception as e:
        print("Warning: config file failed validation with:")
        print(e)
        try:
            shutil.copy2("Config/AviaNZconfig.txt", configdir)
        except Exception as e:
            print("ERROR: failed to copy essential config files")
            print(e)
            raise

    # check and if needed copy any other necessary files
    necessaryFiles = [
        "ListCommonBirds.txt",
        "ListDOCBirds.txt",
        "ListBats.txt",
    ]
    for f in necessaryFiles:
        if not os.path.isfile(os.path.join(configdir, f)):
            print("File %s not found in config dir, providing default" % f)
            try:
                shutil.copy2(os.path.join("Config", f), configdir)
            except Exception as e:
                print("ERROR: failed to copy essential config files")
                print(e)
                raise

    if cli:
        if (cheatsheet or zooniverse) and isinstance(infile, str):
            import AviaNZ

            avianz = AviaNZ(
                configdir=configdir,
                CLI=True,
                cheatsheet=cheatsheet,
                zooniverse=zooniverse,
                firstFile=infile,
                imageFile=imagefile,
                command=command,
            )
            print("Analysis complete, closing PAMalyzer")
        else:
            print("ERROR: valid input file (-f) is needed")
            raise
    else:
        task = None
        print("Starting PAMalyzer in GUI mode")
        from PyQt5.QtWidgets import QApplication

        app = QApplication(sys.argv)
        # a hack to fix default font size (Win 10 suggests 7 pt for QLabels for some reason)
        QApplication.setFont(QApplication.font("QMenu"))

        while True:
            import AviaNZ_manual

            avianz = AviaNZ_manual.AviaNZ(configdir=configdir)

            if avianz:
                avianz.activateWindow()
            else:
                return

            out = app.exec_()
            QApplication.closeAllWindows()
            QApplication.processEvents()

            if out == 0:
                break

try:
    mainlauncher()
except Exception:
    import traceback

    print(traceback.format_exc())
    input(
        "Encountered error. Report it with the text above to PAMalyzer team.\nPress ENTER to exit"
    )
    raise
