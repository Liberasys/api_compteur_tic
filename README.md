**api_compteur_tic : Décoder les trames des compteurs électriques via leur sortie TIC, rendre accessible les valeurs via API WEB sous forme JSON.**

# Installation :
```bash
# en tant que root :
apt-get install python-serial python-flask
cd /opt/
git clone https://github.com/Liberasys/api_compteur_tic.git
cd api_compteur_tic/
chmod 755 api_compteur_tic.py
chmod 755 api_compteur_tic.py
```

# Configuration :
Voir fichier de référence : api_compteur_tic.conf

# Lancement automatique par systemd :
```bash
# en tant que root :
cat << 'EOF' > /etc/systemd/system/api_compteur_tic.service
[Unit]
Description=API pour compteur electrique via TIC
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/api_compteur_tic
ExecStart=/usr/bin/python ./api_compteur_tic.py

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable api_compteur_tic
systemctl start api_compteur_tic
```

# Utilisation :
- obtenir une donnée unitaire (remplacer TARIF et ETIQUETTE) : http://127.0.0.1:5000/get_donnee?tarif=TARIF&etiquette=ETIQUETTE
- obtenir l'interpretation complete des trames : http://127.0.0.1:5000/get_interpretation

# TODO
  - Automatiser la gestion de configuration avec un paquet python.
  - Avant passage en héritage de classe, (solution temporaire). Passer les Classes communes à des paquets et qui font le même traitement dans un paquet à part.
  - Passer en héritage de classe pour les classes de gestion de décodage et d'interpretation des trames.
  - Gérer le dictionnaire de données du pickler lors du reimport, car changement de type de compteur (test de type/version, ne pas prendre en compte les données du fichier pickler le cas échéant, écraser le fichier pickler).
  - Décodage des trames
    - A vérifier, certaines trames du linky ne sont pas correctes. Il manque parfois le checksum en fin de groupe de caractere, champ rencontré : 'SMAXSN-1'. Cas observé une fois.
  - Interpretation des trames
    - Gérer le registre de statuts qui est un champ de bit (Champ STGE), et les autres champs de bits, dans l'interpreteur de trame pour compteur Linky, voir doc.
