# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 2016/09
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

import sys
import getopt
import serial
import copy

from flask import Flask, request, jsonify

from decode_pmepmi import LecturePortSerie
from decode_pmepmi import LectureFichier
from decode_pmepmi import DecodeCompteurPmePmi
from decode_pmepmi import InterpretationTramesPmePmi
from decode_pmepmi import SortieFichier


from pickler import PicklesMyData
from affichage import AfficheTrames
from affichage import AfficheInterpretations

########################################################################
# MAIN
########################################################################

type_comteur = 'linky'

lecture_serie_active = False
lecture_fichier_active = True

sortie_fichier_active = False
affichage_sortie_standard_active = False
affichage_trames_gui_active = False
interpretation_des_trames = True
tableau_des_trames = []
affichage_interpretations_gui_active = False
tableau_des_interpretations = []

app = Flask(__name__)


if lecture_serie_active == True:
    try:
        print("Initialisation du port serie")
        lien_serie = serial.Serial(port = '/dev/ttyACM0',
                                   baudrate = 115200,
                                   bytesize=serial.SEVENBITS,
                                   parity=serial.PARITY_EVEN,
                                   stopbits=serial.STOPBITS_ONE,
                                   xonxoff=False,
                                   rtscts=False,
                                   dsrdtr=False,
                                   timeout=1)

    #    lien_serie = serial.Serial(port = '/dev/ttyUSB0',
    #                               baudrate = 1200,
    #                               bytesize=serial.SEVENBITS,
    #                               parity=serial.PARITY_EVEN,
    #                               stopbits=serial.STOPBITS_ONE,
    #                               xonxoff=False,
    #                               rtscts=False,
    #                               dsrdtr=False,
    #                               timeout=1)

    #    lien_serie = serial.Serial(port = '/dev/ttyACM0',
    #                               baudrate = 57600,
    #                               timeout=1)
        print("Port serie initialise")
    except serial.SerialException, e:
        print("Probleme avec le port serie : " + str(e))

# Importation des paquets nécessaire au traitement des trames en fonction du type de compteur
# Instanciation des objets avec la classe utilise par le type de compteur
if type_compteur == 'linky':
    from decode_linky import CompteurLinky
    from decode_linky import InterpretationTramesLinky
    decodeur_trames = CompteurLinky()
    interpreteur_trames = InterpretationTramesLinky()
elif type_compteur == 'pmepmi':
    from decode_pmepmi import CompteurPmePmi
    from decode_pmepmi import InterpretationTramesPmePmi
    decodeur_trames = CompteurPmePmi()
    interpreteur_trames = InterpretationTramesPmePmi()

if sortie_fichier_active == True:
    sortie_fichier = SortieFichier()


# Callback appele quand une nouvelle trame est interpretee, applique en interne
# copie la nouvelle trame interpretee dans le tableau des trame interpretees
def cb_nouvelle_trame_interpretee_tt_interpretation(tableau_trame_interpretee):
    tableau_des_interpretations.append(copy.deepcopy(tableau_trame_interpretee))

# Callback appele quand un octet est recu sur le port serie
def cb_nouvel_octet_recu(octet_recu):
    decodeur_trames.nouvel_octet(serial.to_bytes(octet_recu))
    #sortie_fichier.nouvel_octet(serial.to_bytes(octet_recu))

# Callback debut interruption
def cb_debut_interruption():
    print("INTERRUPTION DEBUT !!!!!!")
    interpreteur_trames.incrementer_compteur_interruptions()

# callback fin interruption
def cb_fin_interruption():
    print("Dump interruption : ")
    print(decodeur_trames.get_tampon_interruption())
    print("INTERRUPTION FIN")

# callback mauvaise trame recue
def cb_mauvaise_trame_recue():
    print("Mauvaise trame recue")
    interpreteur_trames.incrementer_compteur_trames_invalides()

# Callback nouvelle trame recue
def cb_nouvelle_trame_recue():
    tableau_des_trames.append(copy.deepcopy(decode_pmepmi.get_derniere_trame_valide()))


# affectation des callbacks :
interpreteur_trames.set_cb_nouvelle_interpretation_tt_interpretation(cb_nouvelle_trame_interpretee_tt_interpretation)
decodeur_trames.set_cb_nouvelle_trame_recue_tt_trame(interpreteur_trames.interpreter_trame)
decodeur_trames.set_cb_fin_interruption(cb_fin_interruption)
decodeur_trames.set_cb_debut_interruption(cb_debut_interruption)
decodeur_trames.set_cb_mauvaise_trame_recue(cb_mauvaise_trame_recue)
decodeur_trames.set_cb_nouvelle_trame_recue(cb_nouvelle_trame_recue)



# Lecture sur port serie
if lecture_serie_active == True:
    # instanciation thread serie
    lecture_serie = LecturePortSerie(lien_serie, cb_nouvel_octet_recu)
    # lancement thread
    lecture_serie.run()


# Lecture depuis fichier
if lecture_fichier_active == True:
    # instanciation thread lecture fichier
    lecture_fichier = LectureFichier(sys.argv[1], cb_nouvel_octet_recu)
    # lancement thread
    print("Debut de decodage du fichier " + sys.argv[1])
    lecture_fichier.run()
    print("Fin du decodage du fichier")


# Sortie GUI d'affichage
if affichage_trames_gui_active == True:
    app = QtGui.QApplication(sys.argv)
    gui_affichage = AfficheTrames(tableau_des_trames)
    sys.exit(app.exec_())
if affichage_interpretations_gui_active == True:
    app = QtGui.QApplication(sys.argv)
    gui_affichage = AfficheInterpretations(tableau_des_interpretations)
    sys.exit(app.exec_())



@app.route('/cptpmepmi/zabbix_autoconf', methods = ['GET'])
def api_cptpmepmi__zabbix_autoconf():
    return jsonify(interpreteur_trames.get_autoconf_zabbix())

@app.route('/cptpmepmi/get_donnee', methods = ['GET'])
def api_cptpmepmi__get_donnee():
    retour = ()
    if 'tarif' in request.args and 'etiquette' in request.args :
        retour = interpreteur_trames.get_donnee(request.args['tarif'],request.args['etiquette'])
        if retour == (None, None):
            return ""
        else:
            return interpreteur_trames.get_donnee(request.args['tarif'],request.args['etiquette'])
    else:
        return "Donner les bons parametres  tarif, etiquette"

app.run(debug=True)
