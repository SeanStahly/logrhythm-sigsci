# logrhythm-sigsci - Import Signal Sciences WAF logs into LogRhythm

This python script will pull down all requests using the [Signal Sciences Data Extration API](https://docs.signalsciences.net/developer/extract-your-data) and store them in local flat files.  Instructions included on how to set up LogRhythm MPE rules to parse the resulting files.

Some of the major features over the SigSci reference implementation are:
 * Rather than expecting to be ran once per hour, the script will keep track of what it last downloaded, and pick up where it left off from.  You can run it once every 5 minutes, once every four hours, or once a day.  I recommend more frequent runs as it ensures that LogRhythm can alert on potential attacks earlier.  It also gives you more of a buffer if a few runs don't succeed.
 * In cases where many logs are downloaded, care is taken to keep RAM usage down by flusing logs to files regularly.
 * The code works on Windows, Mac, and Linux.
 * The example only logged to STDOUT.  This version implements a TimedRotatingFile logger that will log the messages to individual log files, of which are rotated nightly and kept for 7 days.  This helps ensure that no logs are lost due to truncation, etc, while also ensuring it doesn't eventually fill up the disk.

This script is intended to be run from any operating system that can run Python.  Use cron on Linux, or a scheduled task on Windows.

## Signal Sciences API notes
There are some quirks in the SigSci API, all of them documented at https://docs.signalsciences.net/developer/extract-your-data
 * You cannot download any requests newer than 5 minutes ago from now.  This buffer gives them time to ensure consistency.
 * You cannot download any requests older than 24 hours and 5 minutes ago from now.
 * The time period start and end time must end on an even minute boundary.  Meaning, you can download from 10 minutes ago to 5 minutes ago, but you cannot download from 10 minutes and 30 seconds ago to 5 minutes and 30 seconds ago.
 * The results are not sorted.  This doesn't cause problems for LogRhythm, so there's no need for this script to sort them.

## Performance
On my local Windows workstation, it takes just over 45 seconds to download, parse, and write out 36,500 logs, including the startup time for Python.

## Configure Signal Sciences

Setup the SigSci side of things by doing the following:
 * Update the sigsci.conf file with:
  * The email and password of a user with at least "Observer" rights for the sites you want to download.
  * The name of your corporation in the API.  This is most easily found by looking at the URL in your browser and finding it after /corps/.
  * The name of the sites you want to download in the API.  This is found by navigating to the site in the dashboard, and then finding the name in the URL after /sites/.  

## Installation of LogRhythm-SigSci

### Windows Only - Install Python and download zip file
Download the latest Python3 at https://www.python.org/downloads/windows/

During installation, enable Python for all users, and check the box to update the environment variables.

Then, download the code from this project at https://github.com/justintime/logrhythm-duo/archive/master.zip  Extract the 
zip file.

### Windows Only - Run setup script
To install with the default path of ```C:\LogRhythm\logrhythm-duo```, simply run the included ```resources\setup.ps1``` script **as Administrator**.  Also note, if you're running the LogRhythm SysMon Agent as a dedicated user instead of SYSTEM, please add the user 
to the top of setup.ps1 as indicated in the comments.

### Linux Only - create normal user, setup cron
Since we don't need elevated permissions to run this, let's create a dedicated user.

``` bash
# Create our user:
sudo useradd -d /home/logrhythm -s /bin/bash -m logrhythm
# Create our directory and make logrhythm the owner of it:
sudo mkdir /opt/logrhythm-sigsci && sudo chown logrhythm:logrhythm /opt/logrhythm-sigsci && sudo chmod 700 /opt/logrhythm-sigsci
# Become the new user and clone this repo:
sudo su - logrhythm -c 'git clone https://github.com/justintime/logrhythm-sigsci.git /opt/logrhythm-sigsci'
# Edit sigsci.conf and put in your API credentials and other configs:
sudo nano /opt/logrhythm-sigsci/sigsci.conf
```
### All Platforms - Configure sigsci.conf
Configure the config files [as noted above](#Configure-Signal-Sciences).

### Linux - Configure cron
``` bash
# Create the cronjob:
sudo cp /opt/logrhythm-sigsci/resources/logrhythm-sigsci /etc/cron.d
```

### Windows - Configure Task Scheduler
If you ran the setup script, you should have a scheduled task already running!

####### MARK
---------------------------
## Setup of New Log Source and MPE Parsing Rules in the LogRhythm Console

### Create a new log source type
 1. Deployment Manager -> Tools menu -> Knowledge -> Log Source Type Manager
 1. Click the + button
 1. Fill out the following fields:

  | Field              | Value |
  | -----              | ----- |
  | Name               | Flat File - Duo Security 2FA |
  | Abbreviation       | Duo2FA |
  | Log Format         | Text File |
  | Brief Description  | Duo Security 2FA logs utilizing the Duo Python Client API |
  | Additional Details | Up to you :) |

### Create new MPE rules for the Duo2FA Log Source Type
 1. Deployment Manager -> Tools menu -> Knowledge -> MPE Rule Builder
 1. Open up [MPERules.txt](resources/MPERules.txt) in a viewer.
 1. For each rule in [MPERules.txt](resources/MPERules.txt), create a new rule by:
    1. Clicking the + button.
    1. Select "Flat File - Duo Security 2FA" by expanding "Custom Log Source Types" in the "Log Message Source Type Associations" pane in the top right.
    1. Fill in the Rule Name, Common Event, Rule Status, Brief Description, and Base-rule Regular Expression from [MPERules.txt](resources/MPERules.txt).
      1. For rules that have sub-rules, right-click the grid under the Sub-Rules tab, and click new.
      1. Fill in the Rule Name, Common Event, Rule Status, Brief Description, and Mapping Tags from [MPERules.txt](resources/MPERules.txt).
      1. Click the OK button, and repeat for all sub-rules.
    1. Click the disk icon to save the rule.
   
### Specify the MPE rule sort order
  1. While still in the MPE Rule Editor, click the folder icon to open a rule library.
  1. Type "duo" in the filter box under "Select Log Message Source Type", and click on "Flat File - Duo Security 2FA".
  1. Edit menu -> Edit Base-rule Sorting
  1. Ensure that the rules are in the **EXACT** order as listed in [MPERules.txt](resources/MPERules.txt).
  1. Click the OK button.
  1. Close the Rule Builder window.
  
### Create a Log Processing Policy for the MPE Rule
 1. Deployment Manager -> Log Processing Policies tab
 1. Click the + button to create a new policy.
 1. Select "Custom" from the Record Type Filter, and then select "Flat File - Duo Security 2FA" from the "Log Source Type" pane.
 1. Press the OK button.
 1. Enter "LogRhythm Default" for the Name.
 1. Enter "Duo Security 2FA logs utilizing the Duo Python Client API" for the Brief Description.
 1. Right-click inside the Rules grid and click "Check All Displayed"
 1. Right-click inside the grid and select "Properties"
 1. Click the "Enabled" box, then click the OK button.
 1. Click the OK button to dismiss the MPE Policy Editor window.

## Setup of Duo Log Source in the LogRhythm Console

 1. Deployment Manager -> System Monitors tab, double click the machine running the logrhythm-duo script.
 1. Right click the grid, and select "New".
 1. For the "Log Source Type", select your new "Flat File - Duo Security 2FA" source.
 1. Select "LogRhythm Default" from the Log MPE Policy.
 1. Select the "Flat File Settings" tab.
 1. Put the full path to the log files in the File Path box.  If you used the examples for Linux, you'd 
 use ```/opt/logrhythm-duo/logs/*.log*```
 1. In the "Date Parsing Format" field, select 'Linux Audit Log (Unix time)'
 1. Click the "OK" button.


### Testing
Run the script verbosely from the command line:
``` bash
python logrhythm-duo.py -v
```
You should get some messages about how many logs the script downloaded.  If you did, you're good to go and can configure the script to run from Task Scheduler or Cron

