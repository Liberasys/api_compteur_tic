# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 20190129
# Gautier HUSSON / Christophe PAULIAC / Vincent CABILLIC
# Donne en licence selon les termes de l EUPL V.1.1 (EUPL : European Union Public Licence)
# Voir EUPL V1.1 ici : http://ec.europa.eu/idabc/eupl.html

from __future__ import print_function
from serial import to_bytes
import threading
import time
import os
import string
from collections import defaultdict
import copy
import re
import math
import time
import json
import syslog


########################################################################
class LecturePortSerie(threading.Thread):
    """
    Classe de lecture sur port serie
    Arguments :
      - lien_serie : instance de la classe serial
      - callback : callback appele quand un nouvel octet est recu
    """
    def __init__(self, lien_serie_initialise, callback):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self._lien_serie = lien_serie_initialise
        self._callback = callback
        self._running = False

    def __del__(self):
        pass

    def run(self):
        self._running = True
        while self._running == True:
          self._callback(to_bytes(self._lien_serie.read(size=1)))

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self.__del__()
        if self._lien_serie != None:
            self._lien_serie.close()


########################################################################
class LectureFichier(threading.Thread):
    """
    Classe de lecture d'un fichier
    Classe de lecture d'un fichier
    Arguments :
      - chemin_fichier : chemin complet du fichier a lire
      - callback : callback appele quand un nouvel octet est lu
    """
    def __init__(self, chemin_fichier, callback):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self._chemin_fichier = chemin_fichier
        self._callback = callback
        self._running = False
        try:
            self._fichier = open(self._chemin_fichier, "rb")
        except IOError, e:
            print("Impossible d'ouvrir le fichier en lecture : " + str(e))
            syslog.syslog(syslog.LOG_CRIT, "Impossible d'ouvrir le fichier en lecture : " + str(e))
        self._running = True

    def __del__(self):
        pass

    def run(self):
        octet_lu = ''
        self._running = True
        while self._running == True:
            #time.sleep(0.002)
            octet_lu = None
            octet_lu = self._fichier.read(1)
            if octet_lu != b'':
                self._callback(octet_lu)
            else:
                self._fichier.close()
                self._running = False

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self.__del__()
        if self._fichier != None:
            self._fichier.close()

########################################################################
class DecodeCompteurPmePmi():
    """
    Classe de decodage des trames des compteurs EDF type PME-PMI
    """
    def __init__(self):
        self._CHAR_STX = to_bytes("02".decode('hex'))
        self._CHAR_ETX = to_bytes("03".decode('hex'))
        self._CHAR_LF = to_bytes("0A".decode('hex'))
        self._CHAR_CR = to_bytes("0D".decode('hex'))
        self._CHAR_EOT = to_bytes("04".decode('hex'))
        self._CHAR_SEPARATEUR = to_bytes("20".decode('hex'))
        self._dict_char_speciaux = {self._CHAR_STX : "STX",
                                    self._CHAR_ETX : "ETX",
                                    self._CHAR_LF : "LF",
                                    self._CHAR_CR : "CR",
                                    self._CHAR_EOT : "EOT",
                                    self._CHAR_SEPARATEUR : "ESPACE"}

        self._ID_ETAT_ATTENTE_DEBUT_TRAME = 1
        self._ID_ETAT_ATTENTE_DEBUT_GROUPE = 2
        self._ID_ETAT_TRAITEMENT_GROUPE = 3
        self._ID_ETAT_INTERRUPTION = 4
        self._dict_etat = {self._ID_ETAT_ATTENTE_DEBUT_TRAME : "Attente debut trame",
                           self._ID_ETAT_ATTENTE_DEBUT_GROUPE : "Attente debut groupe",
                           self._ID_ETAT_TRAITEMENT_GROUPE : "Traitement groupe",
                           self._ID_ETAT_INTERRUPTION : "Interruption"}

        self._dict_transitions = defaultdict(dict)
        self._dict_fonctions_etats = defaultdict(dict)

        self._etat = self._ID_ETAT_ATTENTE_DEBUT_TRAME
        self._etat_precedent = self._ID_ETAT_ATTENTE_DEBUT_TRAME

        self._dernier_octet = " "
        self._tampon_groupe = ""
        self._tampon_interruption = ""
        self._tampon_derniere_interruption = ""

        self._checksums_groupes_bons = False


        # tableau de la trame, de la forme :
        #[ ('ADS', '041436028024'),
        #  ('MESURES1', 'BT 4 SUP36'),
        #  ...
        #]
        self._t_trame_en_cours = []
        self._t_derniere_trame_valide = []

        # On met les callbacks a False par defaut pour signifier la non affectation
        self.__cb_debut_interruption = False
        self.__cb_fin_interruption = False
        self.__cb_mauvaise_trame_recue = False
        self.__cb_nouvelle_trame_recue = False
        self.__cb_nouvelle_trame_recue_tt_trame = False

        # Initialisation des dictionnaires de traitement de machine a etats
        self.__f_init_dict_transitions()
        self.__f_init_dict_fonctions_etats()

    # Definition des fonctions d'affectation de callbacks
    def set_cb_debut_interruption(self, fonction):
        self.__cb_debut_interruption = fonction

    def set_cb_fin_interruption(self, fonction):
        self.__cb_fin_interruption = fonction

    def set_cb_mauvaise_trame_recue(self, fonction):
        """ Affectation du callback sur mauvaise trame recue """
        self.__cb_mauvaise_trame_recue = fonction

    def set_cb_nouvelle_trame_recue(self, fonction):
        self.__cb_nouvelle_trame_recue = fonction

    def set_cb_nouvelle_trame_recue_tt_trame(self, fonction):
        self.__cb_nouvelle_trame_recue_tt_trame = fonction

    def get_derniere_trame_valide(self):
        """ Obtention de la derniere trame valide """
        return self._t_derniere_trame_valide

    def get_tampon_interruption(self):
        """ Obtention du tampon d'interruption """
        return self._tampon_derniere_interruption

    def __f_init_dict_transitions(self):
        """
        Initialisation du dictionnaire des transitions
        Une transition vers l'etat interruption implique de perdre la trame normale en cours.
        Le dictionnaire est utilise comme suit :
            _dict_transitions = { etat_actuel : { char_entrant : (nouvel_etat, f_depuis_etat_actuel, f_vers_etat_futur, f_depuis_etat_actuel_vers_etat_futur) } }
        Remarque : le programme boucle sur le tuple [1:] pour executer les fonctions du tuple, on peut donc ajouter des fonctions a la chaine !
        """
        self._dict_transitions[self._ID_ETAT_ATTENTE_DEBUT_TRAME]  [self._CHAR_STX] = \
            (self._ID_ETAT_ATTENTE_DEBUT_GROUPE,
             self.__f_noop,
             self.__f_noop,
             self.__f_raz_nouvelle_trame)
        self._dict_transitions[self._ID_ETAT_ATTENTE_DEBUT_TRAME]  [self._CHAR_EOT] = \
            (self._ID_ETAT_INTERRUPTION,
             self.__f_noop,
             self.__f_debut_interruption,
             self.__f_noop)
        self._dict_transitions[self._ID_ETAT_ATTENTE_DEBUT_GROUPE] [self._CHAR_LF]  = \
            (self._ID_ETAT_TRAITEMENT_GROUPE,
             self.__f_noop,
             self.__f_noop,
             self.__f_raz_tampon_groupe)
        self._dict_transitions[self._ID_ETAT_ATTENTE_DEBUT_GROUPE] [self._CHAR_ETX] = \
            (self._ID_ETAT_ATTENTE_DEBUT_TRAME,
             self.__f_noop,
             self.__f_noop,
             self.__f_traitement_fin_de_trame)
        self._dict_transitions[self._ID_ETAT_ATTENTE_DEBUT_GROUPE] [self._CHAR_EOT] = \
            (self._ID_ETAT_INTERRUPTION,
             self.__f_noop,
             self.__f_debut_interruption,
             self.__f_noop)
        self._dict_transitions[self._ID_ETAT_TRAITEMENT_GROUPE]    [self._CHAR_CR]  = \
            (self._ID_ETAT_ATTENTE_DEBUT_GROUPE,
             self.__f_noop,
             self.__f_noop,
             self.__f_traitement_fin_de_groupe)
        self._dict_transitions[self._ID_ETAT_TRAITEMENT_GROUPE]    [self._CHAR_EOT] = \
            (self._ID_ETAT_INTERRUPTION,
             self.__f_noop,
             self.__f_debut_interruption,
             self.__f_noop)
        self._dict_transitions[self._ID_ETAT_INTERRUPTION]         [self._CHAR_ETX] = \
            (self._ID_ETAT_ATTENTE_DEBUT_TRAME,
             self.__f_fin_interruption,
             self.__f_noop,
             self.__f_noop)
        self._dict_transitions[self._ID_ETAT_INTERRUPTION]         [self._CHAR_STX] = \
            (self._ID_ETAT_ATTENTE_DEBUT_GROUPE,
             self.__f_fin_interruption,
             self.__f_noop,
             self.__f_raz_nouvelle_trame)
        self._dict_transitions[self._ID_ETAT_INTERRUPTION]         [self._CHAR_EOT] = \
            (self._ID_ETAT_INTERRUPTION,
             self.__f_fin_interruption,
             self.__f_debut_interruption,
             self.__f_noop)

    def __f_init_dict_fonctions_etats(self) :
        """
        Initialisation des fonctions internes aux etats (sans transition)
        """
        self._dict_fonctions_etats[self._ID_ETAT_ATTENTE_DEBUT_TRAME] = self.__f_noop
        self._dict_fonctions_etats[self._ID_ETAT_ATTENTE_DEBUT_GROUPE] = self.__f_noop
        self._dict_fonctions_etats[self._ID_ETAT_TRAITEMENT_GROUPE] = self.__f_traitement_groupe
        self._dict_fonctions_etats[self._ID_ETAT_INTERRUPTION] = self.__f_interruption

    def __f_noop(self):
        """ Fonction qui ne fait rien """
        pass

    def __f_print_separateur(self):
        """ Fonction d'affichage d'un separateur """
        print("#################################################################################")

    def __f_traitement_groupe(self):
        """ Traitement d'un groupe (= ligne). """
        self._tampon_groupe = self._tampon_groupe + self._dernier_octet

    def __f_interruption(self):
        """ Traitement de l'interruption en cours """
        self._tampon_interruption = self._tampon_interruption + self._dernier_octet

    def __f_debut_interruption(self):
        """ Traitement de debut d'interruption """
        #print("INTERRUPTION debut !!!")
        if self.__cb_debut_interruption != False:
            self.__cb_debut_interruption()
        self.__f_raz_nouvelle_trame()

    def __f_fin_interruption(self):
        """ Traitement de fin d'interruption """
        #print("INTERRUPTION fin.")
        #print(self._tampon_interruption)
        self._tampon_derniere_interruption = self._tampon_interruption
        if self.__cb_fin_interruption != False:
            self.__cb_fin_interruption()

    def __f_traitement_fin_de_trame(self):
        """ Traitement sur fin de trame """
        #print("FIN DE TRAME")
        #print(self._t_trame_en_cours)
        if self._checksums_groupes_bons == True:
            #print("========================== Trame valide : ==========================")
            #print(self._t_trame_en_cours)
            del self._t_derniere_trame_valide[:]
            self._t_derniere_trame_valide = []
            self._t_derniere_trame_valide = copy.deepcopy(self._t_trame_en_cours)
            if self.__cb_nouvelle_trame_recue != False:
                self.__cb_nouvelle_trame_recue()
            if self.__cb_nouvelle_trame_recue_tt_trame != False:
                self.__cb_nouvelle_trame_recue_tt_trame(self._t_derniere_trame_valide)
        else:
            if self.__cb_mauvaise_trame_recue != False:
                self.__cb_mauvaise_trame_recue()


    def __f_raz_nouvelle_trame(self):
        """ Remise a zero des variables pour commencer le traitement d'une nouvelle trame """
        #print("RAZ nouvelle trame")
        self._tampon_groupe = ""
        self._tampon_interruption = ""
        self._checksums_groupes_bons = True
        del self._t_trame_en_cours[:]
        self._t_trame_en_cours = []

    def __f_raz_tampon_groupe(self):
        """ Remise a zero du tampon de groupe """
        #print("RAZ tampon groupe")
        self._tampon_groupe = ""

    def calcule_checksum(self, string):
        """ Calcul du ckecksum """
        sum = 0
        for i in range(len(string)) :
            sum = sum + ord(string[i])
        sum = sum & 0x3F
        sum = sum + 0x20
        return chr(sum)

    def nouvel_octet(self, nouvel_octet):
        """ Traitement d'un octet entrant, fait appel a la machine a etats """
        char_debug=" "
        fonction_transition=None

        self._dernier_octet = to_bytes(nouvel_octet)

        # debug caracteres
        #if self._dernier_octet in self._dict_char_speciaux.keys():
        #    char_debug = self._dict_char_speciaux[self._dernier_octet]
        #else:
        #    char_debug = self._dernier_octet
        #print(str(self._dict_etat[self._etat]) + " : " + char_debug + " 0x" + str(self._dernier_octet.encode('hex')))

        # machine a etat, appelle le dictionnaire de transition, sinon la fonction de traitement de l'etat en cours
        if self._dernier_octet in self._dict_transitions[self._etat]:
            #print("Transition detectee : " + self._dict_etat[self._etat] + " -> " + self._dict_etat[(self._dict_transitions[self._etat][self._dernier_octet][0])])
            #print(str(self._etat) + " -> " + str(self._dict_transitions[self._etat][self._dernier_octet][0]))
            #print(type(self._etat))
            #print(type(self._dict_transitions[self._etat][self._dernier_octet][0]))
            #print(self._dict_transitions[self._etat][self._dernier_octet][1])
            self._etat_precedent = self._etat
            self._etat = self._dict_transitions[self._etat][self._dernier_octet][0]
            for fonction_transition in self._dict_transitions[self._etat_precedent][self._dernier_octet][1:]:
                fonction_transition()
        elif self._etat in self._dict_fonctions_etats:
            self._dict_fonctions_etats[self._etat]()
            #print("Appel fonction ")
            #print(self._dict_fonctions_etats[self._etat])
        else:
            assert("ETAT INDETERMINE, REVOIR CODE OU PROTOCOLE !!!")

    def __f_traitement_fin_de_groupe(self):
        """ Fin de traitement d'un groupe """
        champ_etiquette=""
        champ_donnee=""
        checksum_char=""
        checksum_calcul_chaine=""
        checksum_calcul_resultat=""
        #print("Tampon de groupe : " + self._tampon_groupe)
        # on a besoin de 3 char au minimum
        if (len(self._tampon_groupe) > 3) \
           and (self._checksums_groupes_bons == True):
            checksum_char = self._tampon_groupe[-1:]
            #print("Caractere checksum : " + checksum_char)
            checksum_calcul_chaine = self._tampon_groupe[:-2]
            #print("Chaine checksum : " + checksum_calcul_chaine)
            checksum_calcul_resultat = self.calcule_checksum(checksum_calcul_chaine)
            #print("Checksum calcule : " + checksum_calcul_resultat)
            if checksum_char == checksum_calcul_resultat:
                groupe_caractere_separe = checksum_calcul_chaine.split(self._CHAR_SEPARATEUR)
                champ_etiquette = groupe_caractere_separe[0]
                champ_donnee = groupe_caractere_separe[1]
                #print("Split chaine selon caractere separateur : " + str(groupe_caractere_separe)
                self._t_trame_en_cours.append((champ_etiquette, champ_donnee))
            else:
                self._checksums_groupes_bons = False
        else :
            self._checksums_groupes_bons = False


########################################################################
class InterpretationTramesPmePmi():
    """
    Classe d'interpretation des trames des compteurs EDF type PME-PMI
    """

    def __init__(self):
        # self._dict_interprete, de la forme :
        # { 'HPE': { 'EAP-1_s': ('9256', 'kWh'),
        #            'EAP_s': ('9684', 'kWh'),
        #            ...
        #            'PMAX_s': ('15', 'kVA')},
        #   'INDEP_TARIF': { 'CONSO_TOTALE_i': ('0', None),
        #            'CONSO_TOTALE_s': ('9684', None),
        #             ...
        #            'TGPHI_s': ('-2.83', '')}}
        self._dict_interprete = {}

        self._periode_tarifaire_precedente = None
        self._preavis_etat_precedent = False
        self._epoch_derniere_trame_valide = 0

        # Mutex pour proteger l'acces aux donnes self._dict_interprete et self._periode_tarifaire_precedente
        self._mutex_donnees_actif = False

        self._cb_nouvelle_interpretation = None
        self._cb_nouvelle_interpretation_tt_interpretation = None

        # Compteur de trames invalidees par le decodeur
        self._nbr_trames_invalides = 0
        # tableau de configuration des champs pris en compte
        # <etiquette> : (<est fonction de periode tarifaire>, <est numerique>, <faire le delta / non croissant continu>, <description>, <periode mesures zabbix>, <type donnee zabbix>)
        # <type donnee zabbix> =
        self._zbxtype_int = "int"
        self._zbxtype_float = "float"
        self._zbxtype_char = "char"
        self._zbxtype_text = "text"
        self._zbxtype_log = "log"
        self._config_champs = {"ADS":      (False, False, None, "Identifiant du compteur", 3600, self._zbxtype_text),
                               "CONTRAT":  (False, False, None, "Indique le contrat souscrit", 3600, self._zbxtype_text),
                               "DATE":     (False, False, None, "Date et heure courrante", 30, self._zbxtype_text),
                               "EA_s":     (False, True,  True, "Energie active soutiree au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "ER+_s":    (False, True,  True, "Energie reactive positive soutiree au primaire, delta entre deux trames", 10, self._zbxtype_int),
                               "ER-_s":    (False, True,  True, "Energie reactive negative soutiree au primaire, delta entre deux trames", 10, self._zbxtype_int),
                               "EAPP_s":   (False, True,  True, "Energie apparente soustiree au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "EA_i":     (False, True,  True, "Energie active injectee au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "ER+_i":    (False, True,  True, "Energie reactive positive injectee au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "ER-_i":    (False, True,  True, "Energie reactive negative injectee au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "EAPP_i":   (False, True,  True, "Energie apparente injectee au primaire, delta entre deux trames", 30, self._zbxtype_int),
                               "PTCOUR1":  (False, False, None, "Periode tarifaire courante", 3600, self._zbxtype_text),
                               "TARIFDYN": (False, False, None, "Presence du signal tarifaire exerne", 3600, self._zbxtype_text),
                               "ETATDYN1": (False, False,  False, "Libelle de la periode tarifaire de la periode dynamique en cours", 3600, self._zbxtype_text),
                               "DebP":     (False, False, None, "Date et heure de debut de la periode P", 3600, self._zbxtype_text),
                               "EAP_s":    (True,  True,  False, "Energie active soutiree cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "ER+P_s":   (True,  True,  False, "Energie reactive soutiree positive cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "ER-P_s":   (True,  True,  False, "Energie reactive soutiree negative cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "EAP_i":    (True,  True,  False, "Energie active injectee cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "ER+P_i":   (True,  True,  False, "Energie reactive positive injectee cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "ER-P_i":   (True,  True,  False, "Energie reactive negative injectee cumulee, pour la periode tarifaire en cours", 60, self._zbxtype_int),
                               "DebP-1":   (False, False, None, "Date et heure de debut de la periode P-1", 3600, self._zbxtype_text),
                               "FinP-1":   (False, False, None, "Date et heure de fin de la periode P-1", 3600, self._zbxtype_text),
                               "EAP-1_s":  (True,  True,  False, "Energie active soustiree cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "ER+P-1_s": (True,  True,  False, "Energie reactive positive soustiree cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "ER-P-1_s": (True,  True,  False, "Energie reactive negative soustiree cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "EAP-1_i":  (True,  True,  False, "Energie active injectee cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "ER+P-1_i": (True,  True,  False, "Energie reactive positive injectee cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "ER-P-1_i": (True,  True,  False, "Energie reactive negative injectee cumulee pour la periode tarifaire en cours, arretee a la fin de la periode P-1", 3600, self._zbxtype_int),
                               "PS":       (False, True,  False, "Puissance souscrite pour la periode tarifaire en cours", 3600, self._zbxtype_int),
                               "PA1MN":    (False, True,  False, "Puissance active moyennee sur 1 mn", 60, self._zbxtype_int),
                               "PMAX_s":   (True,  True,  False, "Puissance maximale atteinte en soutirage d'energie active pour la periode tarifaire en cours", 3600, self._zbxtype_int),
                               "TGPHI_s":  (False, True,  False, "Tangente phi moyenne (sur 10mn) en periode de soutirage d'energie active", 300, self._zbxtype_float),
                               "PMAX_i":   (True,  True,  False, "Puissance maximale atteinte en injection d'energie active pour la periode tarifaire en cours", 3600, self._zbxtype_int),
                               "TGPHI_i":  (False, True,  False, "Tangente phi moyenne (sur 10mn) en periode d'injection d'energie active", 300, self._zbxtype_float),
                               # ajoute : compteur d'interruptions, compteur de preavis, puissance totale, compteur trames invalides :
                               # ajout pour utiliser le champ description dans l'autoconfiguration Zabbix
                               # donnees non interpretees dans les trames entrantes, on met False dans les options.
                               "CPT_INTERRUPTIONS":  (False, False, False, "Nombre d'interruptions", 60, self._zbxtype_int),
                               "CPT_PREAVIS":  (False, False, False, "Compteur du nombre de fois ou le preavis de depassement de consommation a ete emis (90% puissance max)", 60, self._zbxtype_int),
                               "CONSO_TOTALE_s":(False, False, False, "Puissance totale consommee, tous tarifs confondus", 60, self._zbxtype_int),
                               "CONSO_TOTALE_i":(False, False, False, "Puissance totale injectee, tous tarifs confondus", 60, self._zbxtype_int),
                               "CPT_TRAMES_INVALIDES" :(False, False, False, "Nombres de trames invalides", 60, self._zbxtype_int)}

    def interpreter_trame(self, trame):
        """ Fonction d'interpretation d'une trame """
        # dict_separation_mesures, de la forme :
        # { 'ID_COMPTEUR': ('041436028024', None),
        #   'MESURES1': { 'CONTRAT': ('BT 4 SUP36', None),
        #                 'DATE': ('26/08/16 21:49:58', None),
        #                 'DebP': ('14/08/16 02:50:00', None),
        #                 ...
        #                 'TGPHI_s': ('-2.83', '')},
        #   'MESURES2': { 'CONTRAT': ('BT 4 SUP36', None)}}
        dict_separation_mesures = {}
        index = 0
        etiquette = " "
        donnee = " "
        tampon = " "
        regexp = None
        liste_vals_numeriques = []
        valeur_numerique = ""
        valeur_numerique_float_ancienne = 0
        valeur_numerique_float_nouvelle = 0
        epoch_ancienne_trame_valide = 0
        unite = " "
        mesure_en_cours = None
        periode_tarifaire = None
        interpretation_valide = True
        # le dict interprete est de la forme :
        # { 'HPE': { 'EAP-1_s': ('9256', 'kWh'),
        #            'EAP_s': ('9684', 'kWh'),
        #            ...
        #            'PMAX_s': ('15', 'kVA')},
        #   'INDEP_TARIF': { 'CONSO_TOTALE_i': ('0', None),
        #            'CONSO_TOTALE_s': ('9684', None),
        #             ...
        #            'TGPHI_s': ('-2.83', '')}}
        nouveau_tableau_interprete = copy.deepcopy(self._dict_interprete)
        nouveau_tableau_interprete_entree_en_cours = ""
        total_conso_indep_tarif_s = 0
        total_conso_indep_tarif_i = 0
        cpt_depassement = 0

        # generation d'un dictionnaire separant MESURE1 et MESURE 2 du type :
        # { 'ID_COMPTEUR': ('041436028024', None),
        #   'MESURES1': { 'CONTRAT': ('BT 4 SUP36', None),
        #                 'DATE': ('26/08/16 21:49:58', None),
        #                 'DebP': ('14/08/16 02:50:00', None),
        #                 ...
        #                 'TGPHI_s': ('-2.83', '')},
        #   'MESURES2': { 'CONTRAT': ('BT 4 SUP36', None)}}
        # boucle sur tous les groupes de la trame

        #print(trame)

        for index, (etiquette,donnee)  in enumerate(trame):
            unite = None
            # Traitements specifiques pour champs structurants
            if etiquette == "ADS":
                dict_separation_mesures["ID_COMPTEUR"] = (donnee, None)
            elif etiquette == "MESURES1":
                mesure_en_cours = "MESURES1"
                dict_separation_mesures["MESURES1"] = {}
                dict_separation_mesures["MESURES1"]["CONTRAT"] = (donnee, None)
            elif etiquette == "MESURES2" :
                mesure_en_cours = "MESURES2"
                dict_separation_mesures["MESURES2"] = {}
                dict_separation_mesures["MESURES2"]["CONTRAT"] = (donnee, None)
            # Traitement des autres champs
            elif mesure_en_cours != None:
                # Si l'etiquette correspond a une entree de la table de configuration / selection :
                if etiquette in self._config_champs:
                    # Si on a une valeur numerique, on extrait la valeur et l'unite :
                    if self._config_champs[etiquette][1] == True:
                        liste_vals_numeriques = re.findall("[-+]?\d*[\.,]\d+|[-+]?\d+", donnee)
                        regexp = re.compile(",")
                        valeur_numerique = regexp.sub('.', liste_vals_numeriques[0])
                        regexp = re.compile("[-+]?\d*[\.,]\d+|[-+]?\d+")
                        unite = regexp.sub('', donnee, count=1)
                        #print("valeur_numerique (unite) : " + valeur_numerique + " (" + unite + ")")
                        dict_separation_mesures[mesure_en_cours][etiquette] = (valeur_numerique, unite)
                    else:
                        dict_separation_mesures[mesure_en_cours][etiquette] = (donnee, None)
            else:
                print("Attention, cas indetermine !!! etiquette/champ : " + etiquette + " // " + donnee)
                print("Debut du programme sur une trame incomplete ?")
                syslog.syslog(syslog.LOG_WARNING, "Attention, cas indetermine !!! etiquette/champ : " + etiquette + " // " + donnee)
                syslog.syslog(syslog.LOG_WARNING, "Debut du programme sur une trame incomplete ?")
                interpretation_valide = False
                del dict_separation_mesures
                return
        # Si on a pas de champ PTCOUR1 ou pas le champ ID_COMPTEUR, alors la trame n'est pas structurellement valide, on la rejettera
        if (not "MESURES1" in dict_separation_mesures) or \
           (not "PTCOUR1" in dict_separation_mesures["MESURES1"]) or \
           (not "ID_COMPTEUR" in dict_separation_mesures):
            interpretation_valide = False
        else:
            # Determination de la periode tarifaire en cours, en fonction de l'activation du tarif dynamique
            if "TARIFDYN" in dict_separation_mesures["MESURES1"]:
                if dict_separation_mesures["MESURES1"]["TARIFDYN"][0] != "INACTIF":
                    periode_tarifaire_en_cours = dict_separation_mesures["MESURES1"]["PTCOUR1"][0] + "-" + dict_separation_mesures["MESURES1"]["ETATDYN1"][0]
                else:
                    periode_tarifaire_en_cours = dict_separation_mesures["MESURES1"]["PTCOUR1"][0]
            else:
                periode_tarifaire_en_cours = dict_separation_mesures["MESURES1"]["PTCOUR1"][0]


        # si la trame presente le formalisme d'interpretation minimum,
        # on met a jour le tableau de donnees interpretees du type :
        # { 'HPE': { 'EAP-1_s': ('9256', 'kWh'),
        #            'EAP_s': ('9684', 'kWh'),
        #            ...
        #            'PMAX_s': ('15', 'kVA')},
        #   'INDEP_TARIF': { 'CONSO_TOTALE_i': ('0', None),
        #            'CONSO_TOTALE_s': ('9684', None),
        #             ...
        #            'TGPHI_s': ('-2.83', '')}}
        # Si on arrive a obtenir le mutex sur les donnees
        if self.__obtenir_mutex_donnees() == True:
            if interpretation_valide == True and "MESURES1" in dict_separation_mesures:
                #print(dict_separation_mesures)
                # MAJ epoch
                epoch_ancienne_trame_valide = self._epoch_derniere_trame_valide
                self._epoch_derniere_trame_valide = time.time()

                # ajoute des entrees manquantes, affectation specifique de l'ID compteur et de l'abonnement
                if not "INDEP_TARIF" in nouveau_tableau_interprete:
                    nouveau_tableau_interprete["INDEP_TARIF"] = {}
                nouveau_tableau_interprete["INDEP_TARIF"]["ID_COMPTEUR"] = copy.deepcopy(dict_separation_mesures["ID_COMPTEUR"])
                nouveau_tableau_interprete["INDEP_TARIF"]["CONTRAT"] = copy.deepcopy(dict_separation_mesures["MESURES1"]["CONTRAT"])
                if not periode_tarifaire_en_cours in nouveau_tableau_interprete:
                    nouveau_tableau_interprete[periode_tarifaire_en_cours] = {}

                # On boucle sur les elements {etiquette : (donnee, unite)} :
                for etiquette in dict_separation_mesures["MESURES1"]:
                    donnee = dict_separation_mesures["MESURES1"][etiquette][0]
                    unite = dict_separation_mesures["MESURES1"][etiquette][1]
                    # Si l'etiquette est dans le tableau de configuration/selection (mesure de precaution)
                    if etiquette in self._config_champs:
                        # On genere la clef du premier niveau du dictionnaire de sortie, en fonction du tableau de configuration (dependance de la periode tarifaire ou non)
                        if self._config_champs[etiquette][0] == True:
                            nouveau_tableau_interprete[periode_tarifaire_en_cours][etiquette] = (donnee, unite)
                            nouveau_tableau_interprete_entree_en_cours = periode_tarifaire_en_cours
                        else:
                            nouveau_tableau_interprete["INDEP_TARIF"][etiquette] = (donnee, unite)
                            nouveau_tableau_interprete_entree_en_cours = "INDEP_TARIF"

                        # Cas ou on doit traiter une delta entre la valeur precedente et la valeur actuelle
                            if self._config_champs[etiquette][2] == True \
                               and (self._epoch_derniere_trame_valide - epoch_ancienne_trame_valide) < 10:
                                if nouveau_tableau_interprete_entree_en_cours in self._dict_interprete:
                                    if etiquette in self._dict_interprete[nouveau_tableau_interprete_entree_en_cours]:
                                        valeur_numerique_float_ancienne = float(self._dict_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette][0])
                                        valeur_numerique_float_nouvelle = float(nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette][0])
                                        #print(" ancienne / nouvelle : " + str(valeur_numerique_float_ancienne) + " / " + str(valeur_numerique_float_nouvelle))
                                        if (math.fabs(valeur_numerique_float_ancienne) <= math.fabs(valeur_numerique_float_nouvelle)) \
                                            and (self._periode_tarifaire == periode_tarifaire_en_cours):
                                            nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"] = []
                                            if self._config_champs[etiquette][5] == self._zbxtype_int:
                                                nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"] = (str(int(valeur_numerique_float_nouvelle - valeur_numerique_float_ancienne)), unite)
                                            else:
                                                nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"] = (str(valeur_numerique_float_nouvelle - valeur_numerique_float_ancienne), unite)
                                            #print("Delta : " + nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"][0])
                                        #else:
                                            ## choix : si on ne peut pas faire le delta, signifie qu'il n'y a pas de donnees
                                            # on decide de laisser la valeur precedente dans le tableau.
                                            #nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"] = []
                                            #nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours][etiquette + "_delta"] = (None, None)

                # Gestion du preavis
                if not "CPT_PREAVIS" in nouveau_tableau_interprete["INDEP_TARIF"]:
                    nouveau_tableau_interprete["INDEP_TARIF"]["CPT_PREAVIS"] = ("0", None)
                if "PREAVIS1" in dict_separation_mesures["MESURES1"]:
                    if self._preavis_etat_precedent == False:
                        self._preavis_etat_precedent = True
                        cpt_depassement = int(nouveau_tableau_interprete["INDEP_TARIF"]["CPT_PREAVIS"][0])
                        cpt_depassement = cpt_depassement + 1
                        nouveau_tableau_interprete["INDEP_TARIF"]["CPT_PREAVIS"] = (str(cpt_depassement), None)
                    elif self._preavis_etat_precedent == True:
                        self._preavis_etat_precedent = False
                    else:
                        pass

                # Creation etiquette nbr interruptions si besoin
                if not "CPT_INTERRUPTIONS" in nouveau_tableau_interprete["INDEP_TARIF"]:
                    nouveau_tableau_interprete["INDEP_TARIF"]["CPT_INTERRUPTIONS"] = ("0", None)

                # Creation etiquette nbr trames invalides si besoin
                if not "CPT_TRAMES_INVALIDES" in nouveau_tableau_interprete["INDEP_TARIF"] :
                    nouveau_tableau_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = ("0", None)

                # Consommation totale : somme des consos
                for nouveau_tableau_interprete_entree_en_cours in nouveau_tableau_interprete:
                    if nouveau_tableau_interprete_entree_en_cours != "INDEP_TARIF":
                        if "EAP_s" in nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours]:
                            total_conso_indep_tarif_s = total_conso_indep_tarif_s + int(nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours]["EAP_s"][0])
                        if "EAP_i" in nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours]:
                            total_conso_indep_tarif_i = total_conso_indep_tarif_i + int(nouveau_tableau_interprete[nouveau_tableau_interprete_entree_en_cours]["EAP_i"][0])
                if not "CONSO_TOTALE_s" in nouveau_tableau_interprete["INDEP_TARIF"]:
                    nouveau_tableau_interprete["INDEP_TARIF"]["CONSO_TOTALE_s"] = (None, None)
                if not "CONSO_TOTALE_i" in nouveau_tableau_interprete["INDEP_TARIF"]:
                    nouveau_tableau_interprete["INDEP_TARIF"]["CONSO_TOTALE_i"] = (None, None)
                nouveau_tableau_interprete["INDEP_TARIF"]["CONSO_TOTALE_s"] = (str(total_conso_indep_tarif_s), None)
                nouveau_tableau_interprete["INDEP_TARIF"]["CONSO_TOTALE_i"] = (str(total_conso_indep_tarif_i), None)

                # Au final, on recopie le nouveau tableau interprete, et on met a jour la periode tarifaire actuelle
                del self._dict_interprete
                self._dict_interprete = copy.deepcopy(nouveau_tableau_interprete)
                self._periode_tarifaire = periode_tarifaire_en_cours
                #print(self._dict_interprete)
            else:
                print("Attentions : formalisme de trame invalide !!!!")
                syslog.syslog(syslog.LOG_WARNING, "Attentions : formalisme de trame invalide !!!!")

            # On a fini de modifier les donnes, on relache le mutex
            self.__relacher_mutex_donnees()
            # Appel des callback definis
            if interpretation_valide == True:
                if self._cb_nouvelle_interpretation != None:
                    self._cb_nouvelle_interpretation()
                if self._cb_nouvelle_interpretation_tt_interpretation != None:
                    if self.__obtenir_mutex_donnees() == True:
                        #print(self._dict_interprete)
                        self._cb_nouvelle_interpretation_tt_interpretation(self._dict_interprete)
                        self.__relacher_mutex_donnees()
        # Un peu de menage
        del nouveau_tableau_interprete
        del dict_separation_mesures

    def set_cb_nouvelle_interpretation(self, fonction):
        """ Affectation du callback appele quand une nouvelle interpretation est validee """
        self._cb_nouvelle_interpretation = fonction

    def set_cb_nouvelle_interpretation_tt_interpretation(self, fonction):
        """ Affectation du callback appele quand quand une nouvelle interpretation est validee,
            applique sur l'interpretation - passee en parametre du callback
        """
        self._cb_nouvelle_interpretation_tt_interpretation = fonction

    def incrementer_compteur_interruptions(self):
        """ Incrementer le compteur d'interruptions """
        #print("Incrementer le compteur d'interruptions")
        CPT_INTERRUPTIONSerruptions = 0
        if self.__obtenir_mutex_donnees() == True:
            if not "INDEP_TARIF" in self._dict_interprete:
                self._dict_interprete["INDEP_TARIF"] = {}
            if not "CPT_INTERRUPTIONS" in self._dict_interprete["INDEP_TARIF"]:
                self._dict_interprete["INDEP_TARIF"]["CPT_INTERRUPTIONS"] = ("0", None)
            CPT_INTERRUPTIONSerruptions = int(self._dict_interprete["INDEP_TARIF"]["CPT_INTERRUPTIONS"][0])
            CPT_INTERRUPTIONSerruptions = CPT_INTERRUPTIONSerruptions +1
            self._dict_interprete["INDEP_TARIF"]["CPT_INTERRUPTIONS"] = (str(CPT_INTERRUPTIONSerruptions), None)
            self.__relacher_mutex_donnees()

    def incrementer_compteur_trames_invalides(self):
        """ Incrementer le compteur de trames invalides """
        #print("Incrementer le compteur de trames invalides")
        cpt_trames_invalides = 0
        if self.__obtenir_mutex_donnees() == True:
            if not "INDEP_TARIF" in self._dict_interprete:
                self._dict_interprete["INDEP_TARIF"] = {}
            if not "CPT_TRAMES_INVALIDES" in self._dict_interprete["INDEP_TARIF"]:
                self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = ("0", None)
            cpt_trames_invalides = int(self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"][0])
            cpt_trames_invalides = cpt_trames_invalides +1
            self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = (str(cpt_trames_invalides), None)
            self.__relacher_mutex_donnees()

    def __obtenir_mutex_donnees(self):
        """ Obtention de l'exclusivite sur les donnees (mutex) """
        mutex_timeout = 5
        epoch_demarrage = time.time()
        mutex_obtenu = False

        while ((time.time() - epoch_demarrage) < mutex_timeout) and \
              (mutex_obtenu == False):
            if self._mutex_donnees_actif == True:
                print("Essai infructueux d'obtention du mutex des donnees interpretees.")
                syslog.syslog(syslog.LOG_WARNING, "Essai infructueux d'obtention du mutex des donnees interpretees.")
            else:
                mutex_obtenu = True
                self._mutex_donnees_actif = False
                #print("Mutex obtenu")
            time.sleep(0.2)
        return mutex_obtenu


    def __relacher_mutex_donnees(self):
        """ Relache de l'exclusivite sur les donnees """
        self._mutex_donnees_actif = False
        #print("Mutex relache")

    def get_donnee(self, ptarif, etiquette):
        """ Obtenir une donnee
        arguments :
         - ptarif : periode tarifaire demandee ou "INDEP_TARIF"
         - etiquette : etiquette de la donnee voulue
        sortie : un tuple (valeur, unite)
        """
        if self.__obtenir_mutex_donnees() == True:
            if ptarif in self._dict_interprete :
                if etiquette in self._dict_interprete[ptarif]:
                    sortie = copy.deepcopy(self._dict_interprete[ptarif][etiquette])
                else:
                    sortie = (None, None)
            else:
                sortie = (None, None)
            self.__relacher_mutex_donnees()
        else:
            sortie = (None, None)
        return(sortie)

    def get_autoconf_zabbix(self, zbx_type=""):
        """ Obtenir l'autoconfiguration Zabbix """
        # le tableau d'autoconf zabbix est de la forme :
        #{ 'data': [ { '{#DESCRIPTION}': 'Puissance totale injectee, tous tarifs confondus',
        #              '{#ETIQUETTE}': 'CONSO_TOTALE_i',
        #              '{#PTARIF}': 'INDEP_TARIF',
        #              '{#UNITE}': '',
        #              '{#PERIODE}': '60'},
        #            { '{#DESCRIPTION}': 'Date et heure de debut de la periode P-1',
        #              '{#ETIQUETTE}': 'DebP-1',
        #              '{#PTARIF}': 'INDEP_TARIF',
        #              '{#UNITE}': '',
        #              '{#PERIODE}': '30'},
        #            ...
        #            { '{#DESCRIPTION}': 'Energie reactive soutiree negative cumulee, pour la periode tarifaire en cours',
        #              '{#ETIQUETTE}': 'ER-P_s',
        #              '{#PTARIF}': 'HCE',
        #              '{#UNITE}': 'kvarh',
        #              '{#PERIODE}': '60'}]}
        tableau_config = {"data" : []}
        entree_config = {}
        tarif = None
        etiquette = None
        donnee = None
        unite = None
        description = None
        periode = None

        # On demande le mutex et on boucle sur les entrees du tableau de trames interpretees
        if self.__obtenir_mutex_donnees() == True:
            for tarif in self._dict_interprete:
                for etiquette in self._dict_interprete[tarif]:
                    #donnee = self._dict_interprete[tarif][etiquette][0]
                    unite = self._dict_interprete[tarif][etiquette][1]
                    if etiquette in self._config_champs:
                        description = self._config_champs[etiquette][3]
                        periode = self._config_champs[etiquette][4]
                        type_donnee_zabbix = self._config_champs[etiquette][5]
                        # Cas particulier : si on gere un delta, on renvoie le delta, pas la valeur source
                        if self._config_champs[etiquette][2] == True:
                            if (etiquette + "_delta") in self._dict_interprete[tarif] :
                                etiquette = etiquette + "_delta"
                                #donnee = self._dict_interprete[tarif][etiquette][0]
                                unite = self._dict_interprete[tarif][etiquette][1]
                        #if donnee == None:
                        #    donnee = ""
                        if unite == None:
                            unite = ""
                        if description == None:
                            description = ""
                        if periode == None:
                            periode = "60"
                        entree_config = {"{#PTARIF}"      : tarif,
                                         "{#ETIQUETTE}"   : etiquette,
                                         "{#UNITE}"       : unite,
                                         "{#DESCRIPTION}" : description,
                                         "{#PERIODE}"     : periode}
                        if entree_config != {}:
                            if zbx_type != "" and zbx_type != type_donnee_zabbix:
                                pass
                            else:
                                tableau_config["data"].append(copy.deepcopy(entree_config))
                            del entree_config
                            entree_config = {}
        self.__relacher_mutex_donnees()
        #print(tableau_config)
        return tableau_config

    def get_dict_interpretation(self):
        """ Obtenir le dictionnaire d'interpretation """
        #print("Obtenir le dictionnaire d'interpretation")
        if self.__obtenir_mutex_donnees() == True:
            return copy.deepcopy(self._dict_interprete)
            self.__relacher_mutex_donnees()

    def charger_etat_interpretation(self, dict_interpretation):
        """ Charger un dictionnaire d'interpretation """
        #print("Charger un dictionnaire d'interpretation")
        if self.__obtenir_mutex_donnees() == True:
            self._dict_interprete = copy.deepcopy(dict_interpretation)
            self.__relacher_mutex_donnees()


########################################################################
class SortieFichier():
    """
    Classe de sortie fichier
    """
    def __init__(self):
        self._chemin_fichier="./"+time.strftime("%Y%m%d-%H%M%S")+".txt"
        try:
            self._fichier_sortie = open(self._chemin_fichier, "w")
        except IOError:
            print("Probleme a l'ouverture du fichier de sortie")
            syslog.syslog(syslog.LOG_WARNING, "Probleme a l'ouverture du fichier de sortie")
    def nouvel_octet(self, nouvel_octet):
        self._fichier_sortie.write(to_bytes(nouvel_octet))
