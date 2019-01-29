# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 2016/09
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

from PySide import QtGui, QtCore

########################################################################
class AfficheTrames(QtGui.QWidget):
    """
    Classe d'affichage des trames avec un curseur sur le no de trame
    En entree : le tableau de trames
    """
    def __init__(self, tableau_trames):
        super(AfficheTrames, self).__init__()
        self._tableau_trames = tableau_trames
        self._slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
        self._textEdit=QtGui.QTextEdit()
        self._initUI()
        
    def _initUI(self):
        self.setGeometry(300, 300, 1024, 170)
        self._slider.setMinimum(0)
        self._slider.setMaximum(len(self._tableau_trames)-1)
        self._slider.valueChanged[int].connect(self.changeValue)
        self._textEdit.setReadOnly(True)
        self._textEdit.setLineWrapMode(self._textEdit.NoWrap)
        font = self._textEdit.font()
        font.setFamily("Courier")
        font.setPointSize(10)
        self.setWindowTitle('Affiche trames PME-PMI')
        layout= QtGui.QVBoxLayout()
        layout.addWidget(self._slider)
        layout.addWidget(self._textEdit)
        self.setLayout(layout)
        self.show()
        
    def changeValue(self, value):
        index = 0
        etiquette = ""
        donnee = ""
        texte = ""
        for index, (etiquette,donnee)  in enumerate(self._tableau_trames[value]):
            texte = texte + etiquette + " : " + donnee + "\n"
        self._textEdit.setText(texte)


########################################################################
class AfficheInterpretations(QtGui.QWidget):
    """
    Classe d'affichage des interpretations avec un curseur sur le no d'interpretation
    En entree : le tableau d'interpretations
    """
    def __init__(self, tableau_interpretations):
        super(AfficheInterpretations, self).__init__()
        self._tableau_interpretations = tableau_interpretations
        self._slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
        self._textEdit=QtGui.QTextEdit()
        self._initUI()
        
    def _initUI(self):      
        self.setGeometry(300, 300, 1024, 170)
        self._slider.setMinimum(0)
        self._slider.setMaximum(len(self._tableau_interpretations)-1)
        self._slider.valueChanged[int].connect(self.changeValue)
        self._textEdit.setReadOnly(True)
        self._textEdit.setLineWrapMode(self._textEdit.NoWrap)
        font = self._textEdit.font()
        font.setFamily("Courier")
        font.setPointSize(10)
        self.setWindowTitle('Affiche interpretation des trames PME-PMI')
        layout= QtGui.QVBoxLayout()
        layout.addWidget(self._slider)
        layout.addWidget(self._textEdit)
        self.setLayout(layout)
        self.show()
        
    def changeValue(self, value):
        index = 0
        periode_tarifaire = ""
        etiquette = ""
        donnee = ""
        unite = ""
        texte = ""
        
        for periode_tarifaire in self._tableau_interpretations[value]:
            for etiquette in sorted(self._tableau_interpretations[value][periode_tarifaire]):
                donnee = self._tableau_interpretations[value][periode_tarifaire][etiquette][0]
                unite = self._tableau_interpretations[value][periode_tarifaire][etiquette][1]
                if unite == None:
                    unite = ""
                if donnee == None:
                    donnee = ""
                texte = texte + periode_tarifaire + " :: " + etiquette + " : " + donnee + " (" + unite + ")" + "\n"
        self._textEdit.setText(texte)
