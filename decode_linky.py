# Droits d'auteur : HUSSON CONSULTING SAS - Liberasys
# 2016/09
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
      - callback : callback appelle quand un nouvel octet est recu
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
class DecodeCompteurLinky():
    """
    Classe de decodage des trames des compteurs EDF type Linky
    """
    def __init__(self):
        self._CHAR_STX = to_bytes("02".decode('hex'))
        self._CHAR_ETX = to_bytes("03".decode('hex'))
        self._CHAR_LF = to_bytes("0A".decode('hex'))
        self._CHAR_CR = to_bytes("0D".decode('hex'))
        self._CHAR_EOT = to_bytes("04".decode('hex'))
        self._CHAR_SEPARATEUR = to_bytes("09".decode('hex')) # En mode tic historique char_separateur (0x20) : "ESPACE", en tic standard char_separateur(0x09) : "HORIZONTAL TAB"
        self._dict_char_speciaux = {self._CHAR_STX : "STX",
                                    self._CHAR_ETX : "ETX",
                                    self._CHAR_LF : "LF",
                                    self._CHAR_CR : "CR",
                                    self._CHAR_EOT : "EOT",
                                    self._CHAR_SEPARATEUR : "HT"}

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

    ### Begin. A supprimer si il n'y a pas d'interruption
    def set_debut__interruption(self, fonction):
            self.__cb_debut_interruption = fonction

    def set_cb_fin_interruption(self, fonction):
            self.__cb_fin_interruption = fonction
    ### End

    def set_cb_mauvaise_trame_recue(self, fonction):
            """ Affectation du callback sur mauvaise trame recue """
            self.__cb_mauvaise_trame_recue = fonction

    def set_cb_nouvelle_trame_recue(self, fonction):
            self.__cb_nouvelle_trame_recue = fonction

    def set_cb_nouvelle_trame_recue_tt_tramee(self, fonction):
            self.__cb_nouvelle_trame_recue_tt_trame = fonction

    def get_derniere_trame_valide(self):
            """ Obtention de la derniere trame valide """
            return self._t_derniere_trame_valide

    def get_tampon_interruption(self):
            """ Obtention du tampon d'interruption """
            self._tampon_derniere_interrution

    ### Machine à etat à modifier si il n'y a pas d'interruption dans les trames
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

    def __f_init_dict_fonctions_etats(self):
            """
            Initialisation des fonctions internes aux etats (sans transition)
            """
        self._dict_fonctions_etats[self._ID_ETAT_ATTENTE_DEBUT_TRAME] = self.__f_noop
        self._dict_fonctions_etats[self._ID_ETAT_ATTENTE_DEBUT_GROUPE] = self.__f_noop
        self._dict_fonctions_etats[self._ID_ETAT_TRAITEMENT_GROUPE] = self.__traitement_groupe
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
        if self.__cb_debut_interruption != False:
            self.__cb_debut_interruption()
        self.__f_raz_nouvelle_trame()

    def __f_fin_interruption(self):
        """ Traitement de fin d'interruption """
        self._tampon_derniere_interruption = self._tampon_interruption
        if self.__cb_fin_interruption != False:
            self.__cb_fin_interruption()

    def __f_traitement_fin_de_trame(self):
        """ Traitement sur fin de trame """
        if self._checksums_groupes_bons == True:
            del self._t_derniere_trame_valide[:]
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
            # charge dans fonction_transition les fonctions relatives à l'etat actuel et les execute. indice 1 car 0 stocke un nouvel etat
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
        element_groupe_caractere=None
        nombre_element_groupe_caractere=None

        #print("Tampon de groupe : " + self._tampon_groupe)
        # on a besoin de 3 char au minimum
        if (len(self._tampon_groupe) > 3) \
           and (self._checksums_groupes_bons == True):
           # Separation du champ contenant le checksum et du reste des informations. Calcule 
           checksum_char = self._tampon_groupe[-1:]
           #print("Caractere checksum : ", checksum_char)
           checksum_calcul_chaine = self._tampon_groupe[:-1]
           #print("Chaine checksum : ", checksum_calcul_chaine)
           checksum_calcul_resultat = self.calcule_checksum(checksum_calcul_chaine)

           # Separation du groupe de caractere dans un tableau
           element_groupe_caractere = checksum_calul_chaine.split(self._CHAR_SEPARATEUR)
           # On enleve le dernier element du tableau car il es vide. Il correspond au dernier donnee apres le caractere separateur, qui n'est pas suivi d'informationself
           element_groupe_caractere = element_groupe_caractere[:-1]
           # On recupere le nombre d'element du tableau
           nombre_element_groupe_caractere = len(element_groupe_caractere)

            if checksum_char == checksum_calcul_resultat:
                # Grace au nombre d'element, on gere la présence de l'horodatage ou non
                if nombre_element_groupe_caractere = 2
                    champ_etiquette = element_groupe_caractere[0]
                    champ_donnee=element_groupe_caractere[1]

                    self._t_trame_en_cours.append((champ_etiquette, champ_donnee))

                elif nombre_element_groupe_caractere = 3:
                    champ_etiquette = element_groupe_caractere[0]
                    champ_horodatage = element_groupe_caractere[1]
                    champ_donnee = element_groupe_caractere[2]
                    self._t_trame_en_cours.append((champ_etiquette, champ_donnee, champ_horodatage))

                else:
                    self._checksums_groupes_bons = False
            else:
                self._checksums_groupes_bons = False
        else :
            self._checksums_groupes_bons = False



class InterpretationTramesLinky():
    """
    Classe d'interpretation des trames des compteurs EDF type Linky
    """
    def __init__(self):

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
        self._unite_donnee_linky = {none: (None),
                                    wh:   ("Wh"),
                                    varh: ("VArh"),
                                    a:    ("A"),
                                    v:    ("V"),
                                    kva:  ("kVA"),
                                    va:   ("VA"),
                                    w:    ("W")
        }

        # <etiquette> : (<est numerique>, <unite donnee>, <description>)
        self._config_champs = {"ADSC":      (False, self._unite_donnee_linky[none], "Identifiant du compteur"),
                               "VTIC":      (False, self._unite_donnee_linky[none], "Version de la TIC"),
                               "DATE":      (False, self._unite_donnee_linky[none], "Date et heure courante"),
                               "NGTF":      (False, self._unite_donnee_linky[none], "Nom du calendrier tarifaire fournisseur"),
                               "LTARF":     (False, self._unite_donnee_linky[none], "Libellé tarif fournisseur en cours"),
                               "EAST":      (True,  self._unite_donnee_linky[wh],   "Energie active soutirée totale"),
                               "EASF01":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 01"),
                               "EASF02":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 02"),
                               "EASF03":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 03"),
                               "EASF04":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 04"),
                               "EASF05":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 05"),
                               "EASF06":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 06"),
                               "EASF07":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 07"),
                               "EASF08":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 08"),
                               "EASF09":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 09"),
                               "EASF10":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Fournisseur, index 10"),
                               "EASD01":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Distributeur, index 01"),
                               "EASD02":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Distributeur, index 02"),
                               "EASD03":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Distributeur, index 03"),
                               "EASD04":    (True,  self._unite_donnee_linky[wh],   "Energie active soutirée Distributeur, index 04"),
                               "EAIT":      (True,  self._unite_donnee_linky[wh],   "Energie active injectée totale"),
                               "ERQ1":      (True,  self._unite_donnee_linky[varh], "Energie réactive Q1 totale"),
                               "ERQ2":      (True,  self._unite_donnee_linky[varh], "Energie réactive Q2 totale"),
                               "ERQ3":      (True,  self._unite_donnee_linky[varh], "Energie réactive Q3 totale"),
                               "ERQ4":      (True,  self._unite_donnee_linky[varh], "Energie réactive Q4 totale"),
                               "IRMS1":     (True,  self._unite_donnee_linky[a],    "Courant efficace,phase 1"),
                               "IRMS2":     (True,  self._unite_donnee_linky[a],    "Courant efficace,phase 2"),
                               "IRMS3":     (True,  self._unite_donnee_linky[a],    "Courant efficace,phase 3"),
                               "URMS1":     (True,  self._unite_donnee_linky[v],    "Tension efficace,phase 1"),
                               "URMS2":     (True,  self._unite_donnee_linky[v],    "Tension efficace,phase 2"),
                               "URMS3":     (True,  self._unite_donnee_linky[v],    "Tension efficace,phase 3"),
                               "PREF":      (True,  self._unite_donnee_linky[kva],  "Puissance apparentes de référence"),
                               "PCOUP":     (True,  self._unite_donnee_linky[kva],  "Puissance apparente de coupure"),
                               "SINSTS":    (True,  self._unite_donnee_linky[va],   "Puissance apparente Instantanée soutiré"),
                               "SINSTS1":   (True,  self._unite_donnee_linky[va],   "Puissance apparente Instantanée soutiré phase 1"),
                               "SINSTS2":   (True,  self._unite_donnee_linky[va],   "Puissance apparente Instantanée soutiré phase 2"),
                               "SINSTS3":   (True,  self._unite_donnee_linky[va],   "Puissance apparente Instantanée soutiré phase 3"),
                               "SMAXSN":    (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n"),
                               "SMAXSN1":   (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n phase 1"),
                               "SMAXSN2":   (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n phase 2"),
                               "SMAXSN3":   (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n phase 3"),
                               "SMAXSN-1":  (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n-1"),
                               "SMAXSN1-1": (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n-1 phase 1"),
                               "SMAXSN2-1": (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n-1 phase 2"),
                               "SMAXSN3-1": (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum soutirée n-1 phase 3"),
                               "SINSTI":    (True,  self._unite_donnee_linky[va],   "Puissance apparente Instantanée injectée"),
                               "SMAXIN":    (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum injectée n"),
                               "SMAXIN-1":  (True,  self._unite_donnee_linky[va],   "Puissance apparente maximum injectée n-1"),
                               "CCASN":     (True,  self._unite_donnee_linky[w],    "Point n de la courbe de charge active soutirée"),
                               "CCASN-1":   (True,  self._unite_donnee_linky[w],    "Point n-1 de la courbe de charge active soutirée"),
                               "CCAIN":     (True,  self._unite_donnee_linky[w],    "Point n de la courbe de charge active injectée"),
                               "CCAIN-1":   (True,  self._unite_donnee_linky[w],    "Point n-1 de la courbe de charge active injectée"),
                               "UMOY1":     (True,  self._unite_donnee_linky[v],    "Tension moyenne phase 1"),
                               "UMOY2":     (True,  self._unite_donnee_linky[v],    "Tension moyenne phase 2"),
                               "UMOY3":     (True,  self._unite_donnee_linky[v],    "Tension moyenne phase 3"),
                               "STGE":      (False, self._unite_donnee_linky[none], "Registre de Statuts"),
                               "DPM1":      (False, self._unite_donnee_linky[none], "Début Pointe Mobile 1"),
                               "FPM1":      (False, self._unite_donnee_linky[none], "Fin Pointe Mobile 1"),
                               "DPM2":      (False, self._unite_donnee_linky[none], "Début Pointe Mobile 2"),
                               "FPM2":      (False, self._unite_donnee_linky[none], "Fin Pointe Mobile 2"),
                               "DPM3":      (False, self._unite_donnee_linky[none], "Début Pointe Mobile 3"),
                               "FPM3":      (False, self._unite_donnee_linky[none], "Fin Pointe Mobile 3"),
                               "MSG1":      (False, self._unite_donnee_linky[none], "Message Court"),
                               "MSG2":      (False, self._unite_donnee_linky[none], "Message Ultra Court"),
                               "PRM":       (False, self._unite_donnee_linky[none], "PRM"),
                               "RELAIS":    (False, self._unite_donnee_linky[none], "Relais"),
                               "NTARF":     (False, self._unite_donnee_linky[none], "Numéro de l'index tarifaire en cours"),
                               "NJOURF":    (False, self._unite_donnee_linky[none], "Numéro du jour en cours calendrier fournisseur"),
                               "NJOURF+1":  (False, self._unite_donnee_linky[none], "Numéro du prochain jour calendrier fournisseur"),
                               "PJOURF+1":  (False, self._unite_donnee_linky[none], "Profil du prochain jour calendrier fournisseur"),
                               "PPOINTE":   (False, self._unite_donnee_linky[none], "Profil du prochain jour de pointe"),
                               "CPT_PREAVIS":          (False, self._unite_donnee_linky[none], "Compteur de nombre de fois ou le preavis de depassement de consommations a ete emis (90% puissance max)"),
                               "CPT_TRAMES_INVALIDES": (False, self._unite_donnee_linky[none], "Nombre de trames invalides")
        }

    def interpreter_trame(self, trame):
        """ Fonction d'interpretation d'une trame """

        dict_separation_mesures = {}
        index = 0
        etiquette = " "
        donnee = " "
        tampon = " "
        regexp = None
        liste_vals_numeriques = []
        valeurs_numeriques = ""

        valeur_numerique_float_ancienne = 0
        valeur_numerique_float_nouvelle = 0
        epoch_ancienne_trame_valide = 0
        unite =  " "
        mesure_en_cours = None
        interpretation_valide = True

        ###
        nouveau_tableau_interprete = copy.deepcopy(self._dict_interprete)
        nouveau_tableau_interprete_entree_en_cours = ""

        ###
        total_conso_indep_tarif_s = 0
        total_conso_indep_tarif_s = 0

        for index, (etiquette, donnee) in enumerate(trame):
            unite = None
            # Traitement specifiques pour champs structurants
            if etiquette == "ADSC":
                dict_separation_mesures["ID_COMPTEUR"] = (donnee, self._config_champs[etiquette][1])
            elif etiquette == "LTARF":
                mesure_en_cours = "MESURE"
                dict_separation_mesures["MESURE"] = {}
                dict_separation_mesures["MESURE"]["CONTRAT"] = (donnee, self._config_champs[etiquette][1])
            elif etiquette in self._config_champs:
                if self._config_champs[etiquette][0]:
                    # Si la donnee est numerique
                    liste_vals_numeriques = re.findall("[-+]?\d*[\.,]\d+|[-+]?\d+", donnee) # fais correspondre (match) les donnees numérique avec ou sans virgule
                    regexp = re.compile(",")
                    valeur_numerique = regexp.sub('.', liste_vals_numerique[0])
                    regexp = re.compile("[-+]?\d*[\.,]\d+|[-+]?\d+")

                    dict_separation_mesures["MESURE"][etiquette] = (valeur_numerique, self._config_champs[etiquette][1])
                else:
                    # Sinon c'est textuel
                    dict_separation_mesures["MESURE"][etiquette] = (donnee, self._unite_donnee_linky[none])
            else:
                print("Attention, cas indetermine !!! etiquette/champ : " + etiquette + " //" + donnee)
                print("Debut du programme sur une trame incomplete ?")
                syslog.syslog(syslog.LOG_WARNING, "Attention, cas indetermine !!! etiquette/champ : " + etiquette + " //" + donnee)
                syslog.syslog(syslog.LOG_WARNING, "Debut du programme sur une trame incomplete ?")
                interpretation_valide = False
                del dict_separation_mesures
                return

        # Si on a pas de champ ID_COMPTEUR, alors la trame n'est pas structurellement valide, on la rejettera
        if (not "ID_COMPTEUR" in dict_separation_mesures):
            interpretation_valide = False

        # si la trame presente le formalisme d'interpretation minimum,
        # on met à jour le tableau de donnees interpretees du type : ...
        if self.__obtenir_mutex_donnees() == True:
            if interpretation_valide == True and "MESURE" in dict_separation_mesures:

                #MAJ epoch
                epoch_ancienne_trame_valide = self._epoch_derniere_trame_valide
                self._epoch_derniere_trame_valide = time.time()

                # ajoute des entrees manquantes, affectation specifique de l'ID compteur et de l'abonnement
                if not "INDEP_TARIF" in nouveau_tableau_interprete:
                    nouveau_tableau_interprete["INDEP_TARIF"] = {}
                    nouveau_tableau_interprete["INDEP_TARIF"]["ID_COMPTEUR"] = copy.deepcopy(dict_separation_mesures["ID_COMPTEUR"])
                    nouveau_tableau_interprete["INDEP_TARIF"]["CONTRAT"] = copy.deepcopy(dict_separation_mesures["MESURE"]["CONTRAT"])

                # On boucle sur les elements {etiquette : (donnee, unite)}
                for etiquette in dict_separation_mesures["MESURE"]:
                    donnee = dict_separation_mesures["MESURE"][etiquette][0]
                    unite = dict_separation_mesures["MESURE"][etiquette][1]

                    # Si l'etiquette est deja dans le tableau de configuration/selection (mesure de precaution)
                    if etiquette in self._config_champs:
                        nouveau_tableau_interprete["INDEP_TARIF"][etiquette] = (donnee, unite)
                        nouveau_tableau_interprete_entree_en_cours = "INDEP_TARIF"

                # Creation etiquette nbr trames invalides si besoin
                if not "CPT_TRAMES_INVALIDES" in nouveau_tableau_interprete:
                    nouveau_tableau_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = ("0", None)

                # Au final, on recopie le nouveau tableau interprete, et on met a jour la periode tarifaire actuelle
                del self._dict_interprete
                self._dict_interprete = copy.deepcopy(nouveau_tableau_interprete)

            else:
                print("Attentions : formalisme de trame invalide !!!!")
                syslog.syslog(syslog.LOG_WARNING, "Attention: formalisme de trame invalide !!!!")

            # On a fini de modifier les donnees, on relache le mutex

    def set_cb_nouvelle_interpretation(self, fonction):
        """ Affectation du callback appele quand une nouvelle intrepretation est validee,
        applique sur l'interruption - passee en parametre du callback """
        self._cb_nouvelle_interpretation = fonction

    def set_cb_nouvelle_intrepretation_tt_interpretation(self, fonction):
        """ Affectation du callback appele quand une nouvelle interpretation est validee,
            applique sur l'interpretation - passee en parametre du callback
        """
        self._cb_nouvelle_interpretation_tt_interpretation = fonction

    def incrementer_compteur_trames_invalides(self):
        """ Incrementer le compteur de trames invalides """
        #print("Incrementer le compteur de trames invalides")
        cpt_trames_invalides = 0
        if self.__obtenir_mutex_donnees() == True:
            if not "INDEP_TARIF" in self._dict_interprete:
                self._dict_interprete["INDEP_TARIF"] = (None, None)
            if not "CPT_INTERRUPTIONS" in self._dict_interprete["INDEP_TARIF"]:
                self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = ("0", None)
            cpt_trames_invalides = (int(self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"][0]))
            cpt_trames_invalides = cpt_trames_invalides + 1
            self._dict_interprete["INDEP_TARIF"]["CPT_TRAMES_INVALIDES"] = (str(cpt_trames_invalides), None)
            self.__relacher_mutex_donnees()


    def __obtenir_mutex_donnees(self):
        """Obtention de l'exclusivite sur les donnees (mutex) """
        mutex_timeout = 5
        epoch_demarrae = time.time()
        mutex_obtenu = False

        while((time.time() - epoch_demarrage) < mutex_timeout) and \
        (mutex_obtenu == False):
            if self._mutex_donnees_actif == True:
                print("Essai infructueux d'obtention du mutex des donnees interpretees.")
                syslog.syslog(syslog.LOG_WARNING, "Essai infructueux d'obtention du mutex des donnees interpretees.")
            else:
                mutex_obtenu = True
                self._mutex_donnees_actif = False
                #print("Mutex relache") # debug/log
            time.sleep(0.2)
        return mutex_obtenu

    def __relacher_mutex_donnees(self):
        """ Relacher de l'exclusivite sur les donnees """
        self._mutex_donnees_actif = False
        #print("Mutex relache") #debug/log

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
