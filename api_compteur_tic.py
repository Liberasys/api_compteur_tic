#!/usr/bin/python
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
import logging
from pid import PidFile

import urllib
from flask import Flask, request, jsonify, url_for, redirect, escape

from decode_pmepmi import SortieFichier
from pickler import PicklesMyData


########################################################################
# CONFIGURATION
########################################################################

## Permet l afichage des elements correct dans la console ainsi que
# le dictionnaire des variables de sortie
app_debug = False

## conteneur de variable pour fichier api_pmepmi.conf
dicoval={}

## path vers fichier de configuration
conf_path = '/opt/dl_decode_compteur_tic/api_compteur_tic.conf'

## dictionnaire des variables neccessaires a l execution
required = {
            'port':'/dev/ttyUSB0',
            'baudrate':1200,
            'bytesize':serial.SEVENBITS,
            'parity':serial.PARITY_EVEN,
            'stopbits':serial.STOPBITS_ONE,
            'xonxoff':True,
            'rtscts':False,
            'dsrdtr':False,
            'timeout':1,
            'chemin_sauvegarde_interpretation':
                '/opt/dl_decode_compteur_tic/sauvegarde_etat.pkl',
            'periode_sauvegarde': 600,
            'chemin_fichier_pid': '/run/api_compteur_tic.pid',
            'type_compteur': 'linky',
            'sortie_fichier_active': False
            }

## Affiche les elements corrects
def affiche_correct_element(element):
    print('FOUND : "{}" : VALUE = {}'.format(element, dicoval[element]))

## Affiche les elements incorrects
def affiche_incorrect_element(element):
    print('FOUND* : "{}" INCORRECT VALUE = {}, use default value : {}'
        .format(element, dicoval[element], required[element]))

## Affiche les elements neccessaires a l execution mais ne se trouvant
# pas dans le fichier de configuration
def affiche_absent_element(element):
    print('NOT FOUND : "{}" : use default : {}'
        .format(element, required[element]))

## Converti le fichier de configuration
def conversion_fichier(dicoval):

    bytesize_mapping = {
                        '5': serial.FIVEBITS,
                        '6': serial.SIXBITS,
                        '7': serial.SEVENBITS,
                        '8': serial.EIGHTBITS
                        }

    parity_mapping = {
                        'none': serial.PARITY_NONE,
                        'even': serial.PARITY_EVEN,
                        'odd': serial.PARITY_ODD,
                        'mark': serial.PARITY_MARK,
                        'space': serial.PARITY_SPACE
                        }

    stopbits_mapping = {
                        '1': serial.STOPBITS_ONE,
                        '1,5': serial.STOPBITS_ONE_POINT_FIVE,
                        '1.5': serial.STOPBITS_ONE_POINT_FIVE,
                        '2': serial.STOPBITS_TWO
                        }

    boolean_mapping = {
                        'true': True,
                        'True': True,
                        'false': False,
                        'False': False
                        }

    for element in required.keys(): ## parcours des variables obligatoires
        if element in dicoval.keys(): ## parcours des variables du ficher de conf
            if element == 'bytesize':
                if dicoval[element] in bytesize_mapping.keys():
                    if app_debug:
                        affiche_correct_element(element)
                    dicoval[element] = bytesize_mapping[dicoval[element]]
                else:
                    affiche_incorrect_element(element)
                    dicoval[element] = required[element]
            elif element == 'parity':
                if dicoval[element] in parity_mapping.keys():
                    if app_debug:
                        affiche_correct_element(element)
                    dicoval[element] = parity_mapping[dicoval[element]]
                else:
                    affiche_incorrect_element(element)
                    dicoval[element] = required[element]
            elif element == 'stopbits':
                if dicoval[element] in stopbits_mapping.keys():
                    if app_debug:
                        affiche_correct_element(element)
                    dicoval[element] = stopbits_mapping[dicoval[element]]
                else:
                    affiche_incorrect_element(element)
                    dicoval[element] = required[element]
            elif element in ['xonxoff', 'rtscts', 'dsrdtr',
                                'sortie_fichier_active']:
                if dicoval[element] in boolean_mapping.keys():
                    if app_debug:
                        affiche_correct_element(element)
                    dicoval[element] = boolean_mapping[dicoval[element]]
                else:
                    affiche_incorrect_element(element)
                    dicoval[element] = required[element]
            elif element in ['timeout', 'periode_sauvegarde', 'baudrate']:
                try:
                    dicoval[element] = int(dicoval[element])
                    if app_debug:
                        affiche_correct_element(element)
                except ValueError:
                    affiche_incorrect_element(element)
                    dicoval[element] = required[element]
            elif element == 'type_compteur':
                if dicoval[element].lower() in compteur_mapping:
                    if app_debug:
                        affiche_correct_element (element)
                    dicoval[element] = dicoval[element].lower()
            else:
                if app_debug:
                    affiche_correct_element(element)
        else:
            affiche_absent_element(element)
            dicoval[element] = required[element]

try:
    ## Ouverture du fichier de configuration en mode lecture:
    path = open(conf_path,'r')
    ## Recuperation du contenu du fichier:
    lignes = path.readlines()
    ## Traitement ligne par ligne
    for ligne in lignes:
        ## Elimination des commentaires potentiels en fin de ligne:
        sp = ligne.split('#')[0]
        ## Separation variable/valeur:
        sp = sp.split('=')
        ## Si on a plus d'un element, alors on a une affectation valide
        ##   et on la traite.
        if len(sp)>1:
            nom_variable = sp[0].strip("\"\' ")
            valeur_variable = '='.join(sp[1:])
            valeur_variable = valeur_variable.strip("\"\' \n\r")
            dicoval[nom_variable]=valeur_variable

    path.close()
    ## Conversion du fichier :
    conversion_fichier(dicoval)
except IOError:
    ## Fichier non trouve, initialisation des variables par defaut :
    dicoval = required
    print('Fichier non trouve, initialisation des variables par defaut.')

if app_debug:
    print('variables de sortie :')
    # Affiche les elements apres conversion
    for cle,valeur in dicoval.items():
        print(cle, ' = ', valeur, 'type variable :', type(valeur))


########################################################################
# MAIN
########################################################################

# chemin_sauvegarde_interpretation =
# "/opt/dl_decode_pmepmi/sauvegarde_etat.pkl" par defaut
chemin_sauvegarde_interpretation = dicoval['chemin_sauvegarde_interpretation']

# # nbr de secondes entre deux sauvegardes :
# periode_sauvegarde = 600 par defaut
periode_sauvegarde = dicoval['periode_sauvegarde']

# parametrage sortie syslog
syslog.openlog(logoption=syslog.LOG_PID, facility=syslog.LOG_DAEMON)

# # chemin du fichier contenant le PID :
# chemin_fichier_pid = "/run/api_pmepmi.pid" par defaut
chemin_fichier_pid = dicoval['chemin_fichier_pid']

# # activer la sortie fichier ou non
# sortie_fichier_active = False par defaut
sortie_fichier_active = dicoval['sortie_fichier_active']

# # mode de fonctionnement : simulateur ou compteur
mode_fonctionnement = "compteur"

# type de compteur
type_compteur = dicoval['type_compteur']

# # Importation des paquets communs aux deux classes
from decode_pmepmi import LecturePortSerie
from decode_pmepmi import LectureFichier
from decode_pmepmi import SortieFichier

# Importation des paquets necessaire au traitement des trames en fonction du type de compteur
# Instanciation des objets avec la classe utilise par le type de compteur
if type_compteur == 'linky':
    from decode_linky import DecodeCompteurLinky
    from decode_linky import InterpretationTramesLinky
    decodeur_trames = CompteurLinky()
    interpreteur_trames = InterpretationTramesLinky()
elif type_compteur == 'pmepmi':
    from decode_pmepmi import DecodeCompteurPmePmi
    from decode_pmepmi import InterpretationTramesPmePmi
    decodeur_trames = CompteurPmePmi()
    interpreteur_trames = InterpretationTramesPmePmi()

pickles_etat = PicklesMyData(chemin_sauvegarde_interpretation, periode_sauvegarde)
interpreteur_trames = InterpretationTramesPmePmi()
app = Flask(__name__)


########################################################################
# EXECUTION
########################################################################

# contexte du demon et fichier de PID
with PidFile(pidname="api_compteur_tic"):
    def shut_my_app_down(signum, frame):
        """ Arrete proprement l'application """
        print 'Signal handler called with signal', signum
        lecture_serie.close()
        pickles_etat.stop()
        pickles_etat.get_and_pickles_data()
        pickles_etat.close()
        #print("Application erretee, exit 0")
        sys.exit(0)

    signal.signal(signal.SIGHUP, shut_my_app_down)
    signal.signal(signal.SIGINT, shut_my_app_down)
    signal.signal(signal.SIGTERM, shut_my_app_down)

    try:
        print("Initialisation du port serie")
        syslog.syslog(syslog.LOG_INFO, "Initialisation du port serie")
        if mode_fonctionnement == "compteur":
            lien_serie = serial.Serial(port = dicoval['port'],
                                       baudrate = dicoval['baudrate'],
                                       bytesize = dicoval['bytesize'],
                                       parity = dicoval['parity'],
                                       stopbits = dicoval['stopbits'],
                                       xonxoff = dicoval['xonxoff'],
                                       rtscts = dicoval['rtscts'],
                                       dsrdtr = dicoval['dsrdtr'],
                                       timeout = dicoval['timeout'])
        elif mode_fonctionnement == "simulateur":
            lien_serie = serial.Serial(port = '/dev/ttyACM0',
                                       baudrate = 115200,
                                       bytesize=serial.SEVENBITS,
                                       parity=serial.PARITY_EVEN,
                                       stopbits=serial.STOPBITS_ONE,
                                       xonxoff=False,
                                       rtscts=False,
                                       dsrdtr=False,
                                       timeout=1)
        else:
            raise Exception("Mauvais mode de fonctionnement : " + mode_fonctionnement)
        print("Port serie initialise")
        syslog.syslog(syslog.LOG_INFO, "Port serie initialise")
    except serial.SerialException, e:
        print("Probleme avec le port serie : " + str(e) + ", arret du programme")
        syslog.syslog(syslog.LOG_WARNING, "Probleme avec le port serie : " + str(e) + "arret du programme")
        exit(1)

    # Instanciation sortie fichier si besoin
    if sortie_fichier_active == True:
        sortie_fichier = SortieFichier()


    # Callback appele quand un octet est recu
    def cb_nouvel_octet_recu(octet_recu):
        decodeur_trames.nouvel_octet(serial.to_bytes(octet_recu))
        if sortie_fichier_active == True:
            sortie_fichier.nouvel_octet(serial.to_bytes(octet_recu))

    # Callback debut interruption
    def cb_debut_interruption():
        print("INTERRUPTION DEBUT !!!!!!")
        interpreteur_trames.incrementer_compteur_interruptions()

    # callback fin interruption
    def cb_fin_interruption():
        dump_interruption = decodeur_trames.get_tampon_interruption()
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
    decodeur_trames.set_cb_nouvelle_trame_recue_tt_trame(interpreteur_trames.interpreter_trame)
    decodeur_trames.set_cb_mauvaise_trame_recue(cb_mauvaise_trame_recue)
    pickles_etat.set_callback(cb_sauvegarde_etat)

    if type_compteur == 'pmepmi':
            decodeur_trames.set_cb_debut_interruption(cb_debut_interruption)
            decodeur_trames.set_cb_fin_interruption(cb_fin_interruption)

    # lecture de l'etat sauvegarde et demarrage de la sauvegarde periodique :
    etat_sauve = pickles_etat.get_data()
    if etat_sauve != None :
        interpreteur_trames.charger_etat_interpretation(pickles_etat.get_data())
    pickles_etat.start()

    # Lecture sur port serie
    lecture_serie = LecturePortSerie(lien_serie, cb_nouvel_octet_recu)
    lecture_serie.start()

    # parametrage API
    @app.errorhandler(404)
    def page_not_found(error):
        texte = ""
        url = request.url + "zabbix_autoconf"
        description = "autoconfiguration Zabbix (LLD) - parametre optionnel : type (int, float, char, text, log)"
        texte = texte + "<a href=" + url + ">" + url + "</a>" + "   :: " + description + "<br/>"
        url = request.url + "get_donnee?tarif=INDEP_TARIF&etiquette=ID_COMPTEUR"
        description = "obtenir une donnee unitaire"
        texte = texte + "<a href=" + url + ">" + url + "</a>" + "   :: " + description + "<br/>"
        url = request.url + "get_interpretation"
        description = "obtenir l'interpretation complete des trames"
        texte = texte + "<a href=" + url + ">" + url + "</a>" + "   :: " + description + "<br/>"
        return texte

    # API autoconfiguration Zabbix (LLD)
    @app.route('/zabbix_autoconf', methods = ['GET'])
    def api_cptpmepmi__zabbix_autoconf():
        if 'type' in request.args :
            zabbix_type_donnee = request.args['type']
        else:
            zabbix_type_donnee = ""
        return jsonify(interpreteur_trames.get_autoconf_zabbix(zbx_type = zabbix_type_donnee))

    # API de recuperation d'une donnee
    @app.route('/get_donnee', methods = ['GET'])
    def api_cptpmepmi__get_donnee():
        retour = ()
        if 'tarif' in request.args and 'etiquette' in request.args :
            retour = interpreteur_trames.get_donnee(request.args['tarif'],request.args['etiquette'])
            if retour == (None, None):
                return ""
            else:
                return retour[0]
        else:
            return "Donner les bons parametres : tarif=, etiquette="

    # API d'obtention d'un dump du dictionnaire d'interpretation des trames
    @app.route('/get_interpretation', methods = ['GET'])
    def api_cptpmepmi__get_dict_interpretation_trame():
        return jsonify(interpreteur_trames.get_dict_interpretation())

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # lancement API
    app.run(debug=False)





## Configuration Zabbix pour l'API du compteur pmepmi
#UserParameter=custom.discovery.apipmepmi[*],/usr/bin/curl --silent "http://127.0.0.1:5000/zabbix_autoconf?type=$1"
#UserParameter=custom.api.datalogging.pmepmi[*],/usr/bin/curl --silent "http://127.0.0.1:5000/get_donnee?tarif=$1&etiquette=$2"
