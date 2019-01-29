# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 20190129
# Gautier HUSSON / Christophe PAULIAC / Vincent CABILLIC
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

import serial
import threading
import string
import syslog
import sys
import copy
import signal
import atexit
from pid import PidFile

import urllib
from flask import Flask, request, jsonify, url_for, redirect, escape

from affichage import AfficheTrames
from affichage import AfficheInterpretations
# # Importation des paquets communs aux deux classes (pmepmi, linky)
#from decode_pmepmi import LecturePortSerie
from decode_pmepmi import LectureFichier
from decode_pmepmi import SortieFichier

from pickler import PicklesMyData




########################################################################
# MAIN
########################################################################

chemin_sauvegarde_interpretation = "/opt/compteur_tic/sauvegarde_etat.pkl"
periode_sauvegarde = 2 # nbr de secondes entre deux sauvegardes

lecture_serie_active = True
lecture_fichier_active = False

sortie_fichier_active = False

tableau_des_trames = []
tableau_des_interpretations = []

affichage_trames_gui_active = False
affichage_interpretations_gui_active = False

api_cptpmepmi = True

sauvegarde_etat = True

# Type = 'linky', 'pmepmi'
type_compteur = 'linky'

# parametrage sortie syslog
syslog.openlog(logoption=syslog.LOG_PID, facility=syslog.LOG_DAEMON)

# chemin du fichier contenant le PID
chemin_fichier_pid = "/run/api_compteur_tic.pid"

# contexte du demon et fichier de PID
with PidFile(pidname="api_pmepmi"):
    def shut_my_app_down(signum, frame):
        """ Arrete proprement l'application """
        print 'Signal handler called with signal', signum
        if lecture_serie_active == True:
            lecture_serie.close()
        if lecture_fichier_active == True:
            lecture_fichier.close()
        if sauvegarde_etat == True:
            #print("pkl stop")
            pickles_etat.stop()
            #print("pkl pkl")
            pickles_etat.pickles_data()
            #print("pkl close")
            pickles_etat.close()
        #print("Application erretee, exit 0")
        sys.exit(0)

    #atexit.register(shut_my_app_down)
    signal.signal(signal.SIGHUP, shut_my_app_down)
    signal.signal(signal.SIGINT, shut_my_app_down)
    signal.signal(signal.SIGTERM, shut_my_app_down)

    if lecture_serie_active == True:
        try:
            print("Initialisation du port serie")
            syslog.syslog(syslog.LOG_INFO, "Initialisation du port serie")
        #    lien_serie = serial.Serial(port = '/dev/ttyACM0',
        #                            baudrate = 115200,
        #                            bytesize=serial.SEVENBITS,
        #                            parity=serial.PARITY_EVEN,
        #                            stopbits=serial.STOPBITS_ONE,
        #                            xonxoff=False,
        #                            rtscts=False,
        #                            dsrdtr=False,
        #                            timeout=1)
        #
            lien_serie = serial.Serial(port = '/dev/ttyUSB0',
                                       baudrate = 1200,
                                       bytesize=serial.SEVENBITS,
                                       parity=serial.PARITY_EVEN,
                                       stopbits=serial.STOPBITS_ONE,
                                       xonxoff=False,
                                       rtscts=False,
                                       dsrdtr=False,
                                       timeout=1)

        #    lien_serie = serial.Serial(port = '/dev/ttyACM0',
        #                               baudrate = 57600,
        #                               timeout=1)
            print("Port serie initialise")
            syslog.syslog(syslog.LOG_INFO, "Port serie initialise")
        except serial.SerialException, e:
            print("Probleme avec le port serie : " + str(e))
            syslog.syslog(syslog.LOG_WARNING, "Probleme avec le port serie : " + str(e))

    # Instanciation sortie fichier si besoin
    if sortie_fichier_active == True:
        sortie_fichier = SortieFichier()

    # Instanciation API si besoin
    if api_cptpmepmi == True:
        app = Flask(__name__)

    # Instanciation sauvegarde d'etat si besoin
    if sauvegarde_etat == True:
        pickles_etat = PicklesMyData(chemin_sauvegarde_interpretation, periode_sauvegarde)

    # Importation des paquets necessaire au traitement des trames en fonction du type de compteur
    # Instanciation des objets avec la classe utilise par le type de compteur
    if type_compteur == 'linky':
        from decode_linky import DecodeCompteurLinky
        from decode_linky import InterpretationTramesLinky
        decodeur_trames = DecodeCompteurLinky()
        interpreteur_trames = InterpretationTramesLinky()
    elif type_compteur == 'pmepmi':
        from decode_pmepmi import DecodeCompteurPmePmi
        from decode_pmepmi import InterpretationTramesPmePmi
        decodeur_trames = DecodeCompteurPmePmi()
        interpreteur_trames = InterpretationTramesPmePmi()


    # Callback nouvelle trame recue
    def cb_nouvelle_trame_recue():
        tableau_des_trames.append(copy.deepcopy(decode_pmepmi.get_derniere_trame_valide()))
        print("nouvelle trame recue")

    # Callback nouvelle trame interpretee
    # copie la nouvelle trame interpretee dans le tableau des trame interpretees
    def cb_nouvelle_trame_interpretee_tt_interpretation(tableau_trame_interpretee):
        tableau_des_interpretations.append(copy.deepcopy(tableau_trame_interpretee))
        print("nouvelle trame interpretee")

    # Callback appele quand un octet est recu
    def cb_nouvel_octet_recu(octet_recu):
        decode_pmepmi.nouvel_octet(serial.to_bytes(octet_recu))
        if sortie_fichier_active == True:
            sortie_fichier.nouvel_octet(serial.to_bytes(octet_recu))

    # Callback debut interruption
    def cb_debut_interruption():
        print("INTERRUPTION DEBUT !!!!!!")
        interpreteur_trames.incrementer_compteur_interruptions()

    # callback fin interruption
    def cb_fin_interruption():
        dump_interruption = decode_pmepmi.get_tampon_interruption()
        print("Dump interruption : ")
        print(dump_interruption)
        syslog.syslog(syslog.LOG_NOTICE, 'Interruption :')
        syslog.syslog(syslog.LOG_NOTICE, dump_interruption)
        print("INTERRUPTION FIN")

    # callback mauvaise trame recue
    def cb_mauvaise_trame_recue():
        print("Trame invalide recue")
        syslog.syslog(syslog.LOG_NOTICE, "Trame invalide recue")
        interpreteur_trames.incrementer_compteur_trames_invalides()

    # Callback pour la sauvegarde d'etats
    def cb_sauvegarde_etat():
        return interpreteur_trames.get_dict_interpretation()

    # affectation des callbacks :
    if affichage_trames_gui_active == True:
        decode_pmepmi.set_cb_nouvelle_trame_recue(cb_nouvelle_trame_recue)
    if affichage_interpretations_gui_active:
        interpreteur_trames.set_cb_nouvelle_interpretation_tt_interpretation(cb_nouvelle_trame_interpretee_tt_interpretation)
    decode_pmepmi.set_cb_nouvelle_trame_recue_tt_trame(interpreteur_trames.interpreter_trame)
    decode_pmepmi.set_cb_debut_interruption(cb_debut_interruption)
    decode_pmepmi.set_cb_fin_interruption(cb_fin_interruption)
    decode_pmepmi.set_cb_mauvaise_trame_recue(cb_mauvaise_trame_recue)
    if sauvegarde_etat == True:
        pickles_etat.set_callback(cb_sauvegarde_etat)

    # lecture de l'etat sauvegarde et demarrage de la sauvegarde periodique si besoin :
    if sauvegarde_etat == True:
        etat_sauve = pickles_etat.get_data()
        if etat_sauve != None :
            interpreteur_trames.charger_etat_interpretation(pickles_etat.get_data())
        pickles_etat.start()

    # Lecture sur port serie
    if lecture_serie_active == True:
        # instanciation thread serie
        lecture_serie = LecturePortSerie(lien_serie, cb_nouvel_octet_recu)
        # lancement thread
        lecture_serie.start()

    # Lecture depuis fichier
    if lecture_fichier_active == True:
        # instanciation thread lecture fichier
        lecture_fichier = LectureFichier(sys.argv[1], cb_nouvel_octet_recu)
        # lancement thread
        print("Lancement du thread de decodage du fichier " + sys.argv[1])
        lecture_fichier.start()

    # Sortie GUI d'affichage
    if affichage_trames_gui_active == True:
        app = QtGui.QApplication(sys.argv)
        gui_affichage = AfficheTrames(tableau_des_trames)
        sys.exit(app.exec_())
    if affichage_interpretations_gui_active == True:
        app = QtGui.QApplication(sys.argv)
        gui_affichage = AfficheInterpretations(tableau_des_interpretations)
        sys.exit(app.exec_())


    if api_cptpmepmi == True:
        @app.errorhandler(404)
        def page_not_found(error):
            texte = ""
            url = request.url + "zabbix_autoconf"
            description = "autoconfiguration Zabbix (LLD)"
            texte = texte + "<a href=" + url + ">" + url + "</a>" + "   ::   description<br/>"
            url = request.url + "get_donnee?tarif=INDEP_TARIF&etiquette=ID_COMPTEUR"
            description = "obtenir une donnee unitaire"
            texte = texte + "<a href=" + url + ">" + url + "</a>" + "   ::   description<br/>"
            url = request.url + "get_interpretation"
            description = "obtenir l'interpretation complete des trames"
            texte = texte + "<a href=" + url + ">" + url + "</a>" + "   ::   description<br/>"
            return texte

        # API autoconfiguration Zabbix (LLD)
        @app.route('/zabbix_autoconf', methods = ['GET'])
        def api_cptpmepmi__zabbix_autoconf():
            return jsonify(interpreteur_trames.get_autoconf_zabbix())

        # API de recuperation d'une donnee
        @app.route('/get_donnee', methods = ['GET'])
        def api_cptpmepmi__get_donnee():
            retour = ()
            if 'tarif' in request.args and 'etiquette' in request.args :
                retour = interpreteur_trames.get_donnee(request.args['tarif'],request.args['etiquette'])
                if retour == (None, None):
                    return ""
                else:
                    return interpreteur_trames.get_donnee(request.args['tarif'],request.args['etiquette'])
            else:
                return "Donner les bons parametres : tarif=, etiquette="

        # API d'obtention d'un dump du dictionnaire d'interpretation des trames
        @app.route('/get_interpretation', methods = ['GET'])
        def api_cptpmepmi__get_dict_interpretation_trame():
            return jsonify(interpreteur_trames.get_dict_interpretation())

        app.run(debug=False)
