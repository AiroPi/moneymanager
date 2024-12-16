# Money Manager CLI

> [!WARNING]
> Money Manager is under active development. Things can be broken without warning between update. Any suggestion is also welcomed.

Money manager is a CLI app to help you visualise your expenses, your transactions, and also to **group your transactions automatically using rules**.
You can see how much you spend on the "category" you want, during the period you want, etc...

## Install

Moneymanager is a python CLI app, so you will need python installed, and then do:

```bash
pip install git+https://github.com/AiroPi/moneymanager.git -U
```

You can install it in a virtual environnement if you prefer.

### Auto completion

You can enable auto completion for the CLI. This is however not required.

#### Temporarily
```bash
eval $(moneymanager --show-completion)
```

#### Permanently
```bash
moneymanager --install-completion
```

## Usage

### 1. Initialize moneymanager

> [!NOTE]
> Moneymanager needs some config files to work, and store its data in a `data/` folder.
> These files must be present in the directory where **you use the application**.  
> The `init` command can create the config files for you (as empty files).

```bash
moneymanager init
```

This will create the following config files:
- `./groups.yml`
- `./auto_group.yml`
- `./accounts_settings.yml`

And also a `./data/` folder with some files used by the application internally.

### 2. Install the default readers

> [!IMPORTANT]
> Money manager don't comes with pre-installed readers. The readers are not *part* of the app, but the applications *needs* readers to work.
> However, some readers are available in this repo, and can be easily installed using a simple command.

> [!NOTE]
> A __reader__ is a python file containing all the logic to read and parse a bank transactions export file. Each type of export should have a corresponding reader.
> For more informations, check the [reader specifications](https://www.youtube.com/watch?v=dQw4w9WgXcQ).

```bash
moneymanager reader install-default
```

This will create a `./readers/` directory with different python files. You can see the instructions to use theses readers using the following command:
```bash
moneymanager reader instructions ./readers/a_reader.py
```

### 3. Import a file

Once you have read the instructions for a particular bank, make an export and then import it using the command:
```bash
moneymanager import ~/path/to/your/export.csv
```

### 4. Use the application

Read the follwing instruction, and use `moneymanager --help` to get a view of the possibilities!

## Groups

Money manager CLI allows you to create groups in a tree structure. Then, you can assign your transactions to multiple groups.  
But if you have some transactions that have a similarity, and you want to assign them to a particular group, it is possible to do it automatically!

First, create a new group. You can use the following command to proceed:
```bash
moneymanager manage groups
```

This will edit the `groups.yml` file, the `autogroup.yml` file if needed, **and the previously registered associations in the app data**.
> [!IMPORTANT]
> This is why while you can manually create your groups by editing the `groups.yml` file, you should not manually **delete** nor **rename** your groups one created!
> Use the dedicated command for these operations.

### Auto grouping

Open the `autogroup.yml` file. This file has the following structure:
```yml
- group: ...
  rules:
  - ...
```

The available rules are:
```yml
# Test if transaction.{key} == {value}
- type: eq
  key: ...
  value: ...

# Test if transaction.{key} contains {value}
- type: contains
  key: ...
  value: ...

# Test if transaction.{key} contains {value} (insensitively)
- type: icontains
  key: ...
  value: ...

# Test if transaction.{key} starts with {value}
- type: startswith
  key: ...
  value: ...

# Test if any of the rules pass the test
- type: or
  rules:
  - ...

# Test if all of the rules pass the test
- type: and
  rules:
  - ...
```

#### Example

This `auto_group.yml` file will automatically add the group named "Salary" if the transaction label contains the word "your pay" (no matter the case), or if the label starts with the text "Microsoft transfer":
```yml
- group: Salary
  rules:
  - type: or
    rules:
    - type: icontains
      key: label
      value: your pay
    - type: startswith
      key: label
      value: Microsoft transfer
```

## Accounts settings

The `account_settings.yml` allows you to customize a little bit your accounts informations.

### Initial value

Because sometimes, it is not possible to have all the transactions of an account (from its creation), we can set an initial value to an account:
```yaml
initial_values:
- bank: ...
  values:
  - account: ...
    value: ...
```

#### Example

Add 69€ to the account "C/C EUROCOMPTE JEUNE M JOHN DOE" from the bank "Crédit Mutuel":
```yml
initial_values:
- bank: "Crédit Mutuel"
  values:
  - account: "C/C EUROCOMPTE JEUNE M JONH DOE"
    value: 69.00
```

### Aliases

In order to have a nice display name in the different commands, you can add an alias for an account:
```yaml
aliases:
- bank: ...
  values:
  - input: ...
    output: ...
```

