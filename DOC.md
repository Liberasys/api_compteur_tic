# LOGNACT

Fichier :
    - decode_pmepmi.py
    - pickler.py
    - affichage.py
    - api_pmepmi.py
    - api_pmepmi.conf
    - pid.py

Thread :
    - main (api_pmepmi.py)
    - PicklesMyData (pickler.py)
    - LecturePortSerie (decode_pmepmi.py)

## api_pmepmi.py
    Description :
    Programme principal, initialisation des objets et threads.
    Création de l'API.

## api_pmepmi.conf
    Description :
    Fichier de configuration de l'api pmepmi, traitant les trames des compteurs ENEDIS PmePmi
    Paramétrage du port série et de l'application.

## decode_pmepmi.py
    Description :
    Package pour décoder la TIC des compteurs ENEDIS PME-PMI

    Class :
    LecturePortSerie            : Classe de lecture sur port serie
    LectureFichier              : Classe de lecture d'un fichier
    DecodeCompteurPmePmi        : Classe de decodage des trames des compteurs ENEDIS type PME-PMI
    InterpretationTramesPmePmi  : Classe d'interpretation des trames des compteurs ENEDIS type PME-PMI
    SortieFichier               : Classe de sortie fichier

## pickler.py
    Description :
    Package de sauvegarde des données, à intervalle régulier.

    Class :
    PicklesMyData   : Data structure cyclic backup to file class

## affichage.py
    Description :
    Contient les classe d'affichage des trames et interpretations de trames
    Aide au développement, visualisation des trames.

    Class :
    AfficheTrames               : Classe d'affichage des trames avec un curseur sur le no de trame
    AfficheInterpretations      : Classe d'affichage des interpretations avec un curseur sur le no d'interpretation

## pid.py
    Description :
    Package de gestion de démon et fichier PID

Fonctionnement du logiciel :
    Introduction :  
        Ce programme permet le décodage des trames de Télé Information Client (TIC) de compteurs électrique ENEDIS PME-PMI.
        Il y a trois threads :
            - Le main ou sont instanciés les objets nécessaire au traitement, à la configuration de l'API et à la sortie fichier de la trame brut.
            - Le pickler, à intervalle régulier retourne une structure de données dans un fichier de sauvegarde. Il permet de charger cette sauvegarde si besoin.
            - La lecture série récupère les trames en sortie du compteur et appel à traiter chaque nouvel octet envoyé par le compteur.


    Algorithme :
        Après instanciation des objets et des threads, c'est la lecture du lien série qui initie le traitement.
        Chaque nouvel octet reçu de la lecture série est envoyer par fonction de rappel à nouvel_octet(decode_pmepmi).
        L'octet passe dans la machine à état 
