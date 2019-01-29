dl_decode_pmepmi : Décoder les trames des compteurs TIC, rendre accessible les valeurs via API WEB

# Installation :
```bash
# en tant que root :
apt-get install python-serial python-flask  [...]
cd /opt/
git clone https://github.com/Liberasys/dl_decode_pmepmi.git
cd dl_decode_pmepmi/
chmod 755 api_pmepmi.py
./chmod 755 api_pmepmi.py
```

# Configuration :
Voir fichier de référence : api_pmepmi.conf

# Utilisation :
obtenir une donnée unitaire (remplacer TARIF et ETIQUETTE) : http://127.0.0.1:5000/get_donnee?tarif=TARIF&etiquette=ETIQUETTE
obtenir l'interpretation complete des trames : http://127.0.0.1:5000/get_interpretation

# Lancement automatique par systemd :
cat << 'EOF' > /etc/systemd/system/apipmepmi.service
[Unit]
Description=API pour compteur PME/PMI
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/dl_decode_pmepmi
ExecStart=/usr/bin/python ./api_pmepmi.py

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable apipmepmi
systemctl start apipmepmi

# TODO
  - Automatiser la gestion de configuration avec un paquet python.
  - Passer en héritage de classe pour les classes de gestion de décodage et d'interpretation des trames.
  - Gérer le dictionnaire de donnée du pickler lors du reimport, car changement de type de compteur (test de type/version, ne pas prendre en compte les données du fichier pickler le cas échéant, écraser le fichier pickler).
  - Décodage des trames
    - A vérifier, certaines trames du linky ne sont pas correctes. Il manque parfois le checksum en fin de groupe de caractere, champ rencontré : 'SMAXSN-1'.
  - Interpretation des trames
    - Gérer le registre de statuts qui est un champ de bit (Champ STGE), et les autres champs de bits, dans l'interpreteur de trame pour compteur Linky, voir doc.
