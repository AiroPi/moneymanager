# Money Manager CLI

### 0. Install moneymanager

```bash
pip install git+https://github.com/AiroPi/moneymanager.git
```
(Consider using a venv first)

### 1. Create a `groups.yml` file

Example
```yml
- group_name: Revenus récurrents
  subgroups:
  - group_name: Salaire
  - group_name: MobiliJeune
- group_name: Dépenses récurrentes
  subgroups:
  - group_name: Loyer
    subgroups:
    - group_name: "01 avenue des Champs Elysée"
  - group_name: Assurances
    subgroups:
    - group_name: Assurance habitation
- group_name: Vital
  subgroups:
  - group_name: Alimentation
    subgroups:
    - group_name: Courses
- group_name: Trajets
  subgroups:
  - group_name: Train
```

### 2. Create an `auto_group.yml` file

Example
```yml
- group: Salaire
  rules:
    - type: startswith
      value: VIR MONENTREPRISE
      key: label
    - type: eq
      value: Crédit Mutuel
      key: bank_name
- group: "01 avenue des Champs Elysée"
  rules:
  - type: startswith
    value: VIR SEPA LOYER CHAMPS ELYSÉE
    key: label
  - type: eq
    value: Crédit Mutuel
    key: bank_name
- group: Train
  rules:
  - type: icontains
    value: SNCF
    key: label
- group: MobiliJeune
  rules:
  - type: startswith
    value: VIR ACTION LOGEMENT SERVICES
    key: label
- group: Assurance habitation
  rules:
  - type: startswith
    key: label
    value: ASSURANCE HABITATION BF4146755
```

For more informations about the rules types and possibilities, please refer to [the documentation](https://www.youtube.com/watch?v=dQw4w9WgXcQ).


### 3. Create an `account_settings.yml` file

Example
```yml
aliases:
  - bank: "Crédit Mutuel"
    values:
    - input: "LIVRET BLEU M JOHN DOE"
      output: "Livret bleu"
    - input: "C/C EUROCOMPTE JEUNE M JOHN DOE"
      output: "Compte courant"
  - bank: "Société Générale"
    values:
    - input: "0163490857939918"
      output: "Compte courant"
  - bank: "BoursoBank"
    values:
    - input: "02149865523"
      output: "Compte courant"

initial_values:
  - bank: "Crédit Mutuel"
    values:
    - account: "LIVRET BLEU M JONH DOE"
      value: 6000.69
```

### 4. Put all your exports in an `/exports` folder

### 5. Make your own readers, or install the default ones from the repo

```bash
moneymanager install-default-readers
```

### 5. Use the CLI

You can use `moneymanager --help` for more informations.
