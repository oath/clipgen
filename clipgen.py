import gspread
import os, sys
import subprocess
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# Constants 
REENCODING = False
FILEFORMAT = '.mp4'
VERSIONNUM = '0.3.3'
SHEET_NAME = 'data set'
DEBUGGING  = False

SETTINGSLIST = ['REENCODING', 'FILEFORMAT', 'DEBUGGING']

# What is this?
# This script will help quickly cut out video snippets in user reserach videos, based on researcher's timestamps in a spreadsheet!

# TODO
# Quality of life:
#	- Timestamp cleaning doesn't handle: " +H:M:S" either, strip + prefixes?
#	- Command to open the current Sheet in Chrome from the commandline?
#	- Created composite videos with clips from multiple participants?
#	- Title/ending cards?
#	- Being able to select multiple non-continous lines
#	- Add ability to target only one cell. Proposed syntax "P01.11". Should also be batchable, i.e. "P01.11 + P03.11 + P03.09". Should be available directly at (current) mode select stage.
# Programming stuff:
#	- Command line arguments to run everything from a prompt instead of interactively.
#	- Logging of which timestamps are discarded
#	- Expand debug mode (with multiple levels?)
#	- Upgrade to Python 3?
#	- Refactor try statements to be smaller
#	- Support other data formats (Excel, CSV) - would need to re-write parsing backend and refactor code heavily
#	- Rename "generate"-methods to more clearly indicate that they return timestamps to clip (for generate_list(), this method should have a completely different name)
#	- Rename "dumped"-methods once all timestamps are generated from a dumped sheet instead of a live sheet
# Batch improvements:
# 	- Implement the special character to select only one video to be rendered, out of several
# 	- Add support for special tokens like * for starred video clip (this can be added to the dict as 'starred' and then read in the main loop)
# 	- Start using the meta fields for checking which issues are already processesed and what the grouping is
# Major new features:
# 	- GUI
#	- Cropping and timelapsing! For example generate a timelapse of the minimap in TWY or EU.

# Goes through sheet, bundles values from timestamp columns and descriptions columns into tuples.
def generate_list(sheet, mode, type='Default'):
	p = sheet.find('Participants') # Find pariticpant listing coords.
	m = sheet.find('Meta') # Find the meta tag coords.
	s = sheet.find('Summary')
	times = []

	# Sheet dumping to drastically reduce number of calls to Google's API
	# - sheetDump[][] is a list of lists, which forms a matrix
	#             ^    The first list is rows from the Sheet (index starts at 0, which is off by 1 compared to the "real" view)
	#               ^  The second list is columns from the Sheet (index starts at 0, which is off by 1 compared to the "real" view)
	sheetDump = sheet.get_all_values()
	realTime = get_current_time()
	if DEBUGGING: print '! DEBUG Sheet dumped into memory at {0}'.format(realTime)

	# TODO 
	# Add more processing of the title, split out the study number, and project name.
	# Remove hardcoded location and format expectations on study name.
	studyName = sheetDump[0][0] # Find the title of the study, assuming top left in sheet.
	studyName = studyName[0:studyName.find('Data set')-1] # Cut off the stuff we don't want.
	print '\nBeginning work on {0}.'.format(studyName)
	
	# Just some name formatting, after we announced everything up top.
	studyName = studyName.lower()
	studyName = studyName.replace('study ', 'study')
	studyName = studyName[0:studyName.find('study')].replace(' ', '') + '_' + studyName[studyName.find('study'):]
	studyName = studyName.replace(' ', '_') # Replace any leftover whitespace with underscore.
	studyName = unicode(studyName) # Typecast to unicode string to avoid TypeErrors later
	# It should now look like this: 'thundercats_study5'

	# Get number of users, an int that we'll need to efficiently loop through the worksheet.
	userList = sheet.row_values(p.row+1)
	numUsers = get_numusers(userList, p, sheet.col_count)

	if mode == 'batch':
		yn = raw_input('\nWarning: This will generate all possible clips. Do you want to proceed? y/n\n>> ')
		if yn == 'y':
			times = generate_dumpedbatch(sheetDump, p, m, s, numUsers, studyName)
		else:
			pass
	elif mode == 'category':
		category = raw_input('Which category would you like to work in?\n>> ')
		# TODO
		# Wrap the sheet.find() call in a try/except
		# Could also replace the sheet.find() with something similar to the get_dumpedcategory()
		categoryCell = sheet.find(category)
		times = generate_dumpedcategory(sheetDump, p, m, s, numUsers, studyName, categoryCell)
	elif mode == 'line':
		times = generate_line(sheetDump, p, m, s, numUsers, studyName)
	elif mode == 'range':
		while True:
			try:
				startLineSelect = int(raw_input('\nWhich starting line (row number only)?\n>> '))
				endLineSelect = int(raw_input('\nWhich ending line (row number only)?\n>> '))
			except ValueError:
				startLineSelect = int(raw_input('\nTry again. Starting line (row number only)?\n>> '))
				endLineSelect = int(raw_input('\nTry again. Ending line (row number only)?\n>> '))
			# End try/except
			print 'Lines selected: {0} to {1}'.format(sheetDump[startLineSelect-1][s.col-1], sheetDump[endLineSelect-1][s.col-1])
			yn = raw_input('Is this correct? y/n\n>> ')
			if yn == 'y':
				break
			else:
				pass
		# End while
		times = generate_dumpedrange(sheetDump, p, m, s, numUsers, studyName, startLineSelect, endLineSelect)
	elif mode == 'select':
		# WIP + TODO
		# Build this mode. This mode should generate a list of non-completed issues and lets user select from those.
		pass

	return times
# End generate_list()

# Returns int numUsers, how many participant columns exist in the worksheet
def get_numusers(userList, p, colCount):
	# Figure out how many users we have in the sheet (assumes every user is indicated by a 'PXX' identifier)
	numUsers = 0
	for j in range(0, colCount - p.col):
		if len(userList[j]) > 0:
			if userList[j][0] == 'P':
				numUsers += 1
	print 'Found {0} users in total, spanning columns {1} to {2}.'.format(numUsers, p.col, numUsers+p.col)
	return numUsers	
# End get_numusers()

def get_current_time():
	st = str(datetime.now()).split('.')[0]
	return st
# End get_current_time()

def set_program_settings():
	# WIP + TODO
	# Options available, as dicts. Each dicts contains:
	# - name 			The name of the setting, as a string
	# - default 		The default value of the setting, with varying types of values
	# - options 		The available options for the setting, as a list of values
	fileformatOptions = {'name': 'FILEFORMAT', 'default': 'mp4', 'options': ['mp4','flv']}
	reencodingOptions = {'name': 'REENCODING', 'default': False, 'options': [True, False]}
	debuggingOptions  = {'name': 'DEBUGGING', 'default': False, 'options': [True, False]}

	print '\nWhich setting? Available:\n'
	print ', '.join(SETTINGSLIST)
	settingToChange = raw_input('\n>> ')

	print '* Current value for \'{1}\' is \'{0}\''.format(globals()[settingToChange], settingToChange)
	
	newSettingValue = raw_input('\nWhich new value?\n>> ')

	print '* \'{0}\' SET TO \'{1}\''.format(settingToChange, newSettingValue)
		# Reencoding

	# As of right now we are assuming that all settings are global variables.
	if settingToChange != '':
		globals()[settingToChange] = newSettingValue
		return True
	else:
		return False
# End set_program_settings()

def generate_dumpedbatch(sheetDump, p, m, s, numUsers, studyName):
	if DEBUGGING: print '! DEBUG Running method generate_dumpedbatch()'
	times = []
	latestCategory = ''
	for i in range(p.row+1, len(sheetDump)):
		if DEBUGGING: print '! DEBUG Batching on line {0} (real sheet line {1})\n'.format(i, i+1)
		times = times + get_dumpedline(sheetDump, p, m, s, numUsers, i, studyName)
	return times
# End generate_dumpedbatch()

def generate_dumpedcategory(sheetDump, p, m, s, numUsers, studyName, categoryCell):
	if DEBUGGING: print '! DEBUG Starting method generate_dumpedcategory()'

	times = []
	if DEBUGGING: print '! DEBUG Category cell is {0}'.format(categoryCell)
	if DEBUGGING: print '! DEBUG Comparing meta column value \'{0}\' to \'T\''.format(sheetDump[categoryCell.row-1][m.col-1])
	if sheetDump[categoryCell.row-1][m.col-1] == 'T':
		print '+ Found category \'{1}\' on line {0}.'.format(categoryCell.row, sheetDump[categoryCell.row-1][categoryCell.col-1])
		for i in range(categoryCell.row, len(sheetDump)-p.row):
			if sheetDump[i][m.col-1] != 'T':
				times = times + get_dumpedline(sheetDump, p, m, s, numUsers, i, studyName, categoryCell.value)
			else:
				if DEBUGGING: print '\n! DEBUG Encountered category \'{0}\', stopping category batch call'.format(sheetDump[i][s.col-1])
				break
		# End for
	return times
# End generate_dumpedcategory()

def generate_line(sheetDump, p, m, s, numUsers, studyName):
	# This mode generates videos for a single line/row number.
	while True:
		try:
			lineSelect = int(raw_input('\nWhich issue (row number only)?\n>> '))
		except ValueError:
			# TODO
			# This should not be set up this way, make it loop
			lineSelect = int(raw_input('\nTry again. Issue expressed as row number, as integer only.\n>> '))
		print '\nIssue titled: {0}\n'.format(sheetDump[lineSelect-1][s.col-1])
		yn = raw_input('Is this the correct issue? y/n\n>> ')
		if yn == 'y':
			break
		else:
			pass
	# End while

	if DEBUGGING: print '\n! DEBUG Calling get_dumpedline() from generate_line()'
	latestCategory = get_dumpedcategory(sheetDump, lineSelect-1, p.row, m.col, s.col)
	times = get_dumpedline(sheetDump, p, m, s, numUsers, lineSelect-1, studyName, latestCategory)
	if DEBUGGING: print '\n! DEBUG Printing return of get_dumpedline() in generate_line()'
	if DEBUGGING: print times
	
	return times
# End generate_line()

def get_dumpedline(sheetDump, p, m, s, numUsers, lineSelect, studyName, latestCategory=''):
	if DEBUGGING: print '! DEBUG Running method get_dumpedline\n! DEBUG Starting line {0} (real sheet line {1})'.format(lineSelect, lineSelect+1)

	times = []
	if latestCategory == '':
		latestCategory = get_dumpedcategory(sheetDump, lineSelect, p.row, m.col, s.col)
	for i, value in enumerate(sheetDump[lineSelect]):
		if DEBUGGING: print '! DEBUG Item {0} with value \'{1}\' being processesed.'.format(i, value)
		if i <= p.col-1:
			# Don't touch the first 4 columns.
			if DEBUGGING: print '! DEBUG Skipping item {0} with value \'{1}\''.format(i, value)
			pass
		elif i == p.col-1+numUsers-1:
			# Stop iterating once we have gone through all the participants.
			if DEBUGGING: print '! DEBUG Exit for-loop in method get_dumpedline, reached final column {0} (real sheet column {1}).\n'.format(i, i+1)
			break
		elif value is None:
			# Discard empty cells.
			pass
		elif value == '':
			# Discard empty cells.
			pass
		else:
			cell = gspread.models.Cell(lineSelect,i+p.col-1, value)
			if DEBUGGING: print '! DEBUG Found something at step {0}'.format(i)
			issue = { 'cell': cell, 'desc': sheetDump[lineSelect-1][s.col-1], 'study': studyName, 'participant': sheetDump[p.row][i+p.col-2], 'category': latestCategory}
			times.append(issue)
			print '+ Found timestamp: {0}'.format(value.replace('\n',' ')) 
	# End for

	if DEBUGGING: print '! DEBUG Line completed, method get_dumpedline returning list of {0} potential timestamps.\n---'.format(len(times))
	return times
# End get_dumpedline()

def generate_dumpedrange(sheetDump, p, m, s, numUsers, studyName, startLineSelect, endLineSelect):
	times = []
	for i in range(startLineSelect-1, endLineSelect):
		if DEBUGGING: print '! DEBUG Batching on line {0}\n'.format(i)
		times = times + get_dumpedline(sheetDump, p, m, s, numUsers, i, studyName)
	return times
# End generate_dumpedrange()

def get_dumpedcategory(sheetDump, startingRow, pRow, mCol, sCol):
	category = ''
	while category == '':
		try:
			for i in range(startingRow, pRow, -1):
				if sheetDump[i][mCol-1] == 'T': # mCol is a "real" coordinate in the sheet, and is off by one
					category = sheetDump[i][sCol-1] # sCol is a "real" coordinate in the sheet, and is off by one
					print '+ Found category \'{0}\' on line {1}.'.format(category, i+1) # i is accurate to sheetDump but is off by one relative to "real" rows
					break # Exit the for loop so we don't keep going up.
		except IndexError:
			break
		# End try/except
	# End while
	return category
# End get_dumpecdategory()

# Takes a string, returns a double digit number
def double_digits(number):
	try:
		if int(number) < 10:
			return '0' + number
		else:
			return number
	except TypeError:
		# If we can't typecast, we give up
		return number
	# End try/except
# End double_digits()

def filesize(size, precision=2):
    suffixes = ['B','KB','MB','GB','TB']
    suffixIndex = 0
    while size > 1024 and suffixIndex < 4:
        suffixIndex += 1 
        size = size / 1024.0
    return '%.*f%s'%(precision, size, suffixes[suffixIndex])
# End filesize()

# Appends an incremeneted number to the end of files that already exist, if necessary to prevent overwriting clips.
def set_filename(filename):
	step = 1
	while True:
		if os.path.isfile(filename):
			if step < 2:
				suffixPos = filename.find(FILEFORMAT)
				filename = filename[0:suffixPos] + '-' + str(step) + FILEFORMAT
			else:
				dashPos = filename.rfind('-')
				filename = filename[0:dashPos] + '-' + str(step) + FILEFORMAT
			step += 1
		else:
			filename = set_filename_length(filename, step)
			break
	# End while
	return filename
# End set_filename()

def set_filename_length(filename, step=1):
	# Atleast in Windows, filenames should not exceed 255 characters. This method cuts off filenames that might be too long.
	if len(filename) > 255:
		if step > 1:
			if DEBUGGING: print '! DEBUG Filename was longer than 255 chars ({0}, length {1})'.format(filename, len(filename))
			filename = filename[0:255-(1+len(str(step))+len(FILEFORMAT))] + '-' + str(step) + FILEFORMAT
		else:
			filename = filename[0:255-(len(FILEFORMAT))] + FILEFORMAT
	return filename
# End set_filename_length()

def clean_issue(issue):
	timeStamps = []
	unparsedTimes = issue['cell'].value.lower().split()
	if unparsedTimes == issue['cell'].value:
		unparsedTimes = unparsedTimes.split('+').split(',')
	
	# Using own iterator here, instead of letting the for-loop set this up. Otherwise we can't manually advance the iterator (we need to step twice which continue won't do.)
	lines = iter(range(0,len(unparsedTimes)))

	for i in lines:
		if DEBUGGING: print '! DEBUG Cleaning timestamp {0}'.format(unparsedTimes[i])
		unparsedTimes[i] = unparsedTimes[i].strip().rstrip(',').rstrip('-')
		if unparsedTimes[i] == '':
			pass
		elif unparsedTimes[i].find('-') >= 0:
			if unparsedTimes[i][unparsedTimes[i].find('-')-1].isdigit():
				# Slice the timestamp until the dash, and then from after the dash.
				timePair = unparsedTimes[i][0:unparsedTimes[i].find('-')], unparsedTimes[i][unparsedTimes[i].find('-')+1:]
				timeStamps.append(timePair)
		elif unparsedTimes[i].find(':') >= 0:
			if unparsedTimes[i][unparsedTimes[i].find(':')-1].isdigit():
				timePair = unparsedTimes[i], '00:00:00' # We add the zero time so that we will later fire the add_duration for this timestamp
				timeStamps.append(timePair)
		else:
			pass
	# End for

	issue['times'] = timeStamps

	# Are there other characters that will mess up file names? If so, add them here.
	# TODO: This should be reasonable to do with a dictionary/list loop instead of multiple replaces
	issue['desc'] = issue['desc'][ issue['desc'].rfind(']')+1: ].strip()
	issue['desc'] = issue['desc'].replace('\\','-')
	issue['desc'] = issue['desc'].replace('/','-')
	issue['desc'] = issue['desc'].replace('?','_')
	issue['category'] = issue['category'].replace('/','-')
	for forbiddenCharacter in ['\'',
			  '\"',
			  '.',
			  '>',
			  '<',
			  '|',
			  ':']:
		issue['desc'] = issue['desc'].replace(forbiddenCharacter,'')
		issue['category'] = issue['category'].replace(forbiddenCharacter,'')
	# End for
	
	return issue
# End clean_issue()

# Calls ffmpeg to cut a video clip - requires ffmpeg to be added to system or user Path
def ffmpeg(inputfile, outputfile, startpos, outpos, reencode):
	# TODO
	# Protect against videos that have an outtime beyond base video length

	# Makes the clip a minute long if we didn't get an out-time
	if outpos == '00:00:00':
		outpos = add_duration(startpos)

	duration = get_duration(startpos, outpos)

	if duration < 0:
		print 'Can\'t work with negative duration for videos, exiting.'
		sys.exit(0)
	elif duration > 60*5:
		yn = raw_input('This video is over 5 minutes long, do you want to still generate it? (y/n)\n>> ')
		if yn == 'n':
			return None

	print 'Cutting {0} from {1} to {2}.'.format(inputfile, startpos, outpos)
	if DEBUGGING:
		print '! DEBUG Debugging enabled, not attempting to call ffmpeg or output any files.\n  inputfile: {0},\n  outputfile: {1}'.format(inputfile, outputfile)
	else:
		try:
			if not reencode:
				subprocess.call(['ffmpeg', '-y', '-loglevel', '16', '-ss', startpos, '-i', inputfile, '-t', str(duration), '-c', 'copy', '-avoid_negative_ts', '1', outputfile])
			else:
				# If we do this, we will re-encode the video, but resolve all issues with with iframes early and late.
				subprocess.call(['ffmpeg', '-y', '-loglevel', '16', '-ss', startpos, '-i', inputfile, '-t', str(duration), outputfile])
			print '+ Generated video \'{0}\' successfully.\n File size: {1}\n Expected duration: {2} s\n'.format(outputfile, filesize(os.path.getsize(outputfile)), duration)
			return True
		except WindowsError as e:
			print '\n! ERROR ffmpeg could not successfully run.\n  clipgen returned the following error:\n  {0}\n  - Attempted location: \'{3}\'\n  - Attemped inputfile: \'{1}\',\n  - Attempted outputfile: \'{2}\'\n'.format(e, inputfile, outputfile, os.getcwd())
			return False
		# End try/except
# End ffmpeg()

# Returns the duration of a clip as seconds
def get_duration(intime, outtime):
	duration = 0
	try:
		intimeDatetime = datetime.strptime(intime,'%H:%M:%S')
		outtimeDatetime = datetime.strptime(outtime,'%H:%M:%S')
	except ValueError as e:
		print '* Timestamp formatting error was caught.'
		print e
		try:
			intimeDatetime = datetime.strptime(intime,'%H:%M:%S.%f')
			outtimeDatetime = datetime.strptime(outtime,'%H:%M:%S.%f')
		except ValueError as e:
			print '* Further timestamp formatting error was caught, exiting.'
			print '* Timestamp formats need to match each other.'
			print e
			sys.exit(0)
	# End try/except

	hDelta = (outtimeDatetime.hour - intimeDatetime.hour)*60*60
	mDelta = (outtimeDatetime.minute - intimeDatetime.minute)*60
	sDelta = (outtimeDatetime.second - intimeDatetime.second)
	duration = hDelta + mDelta + sDelta

	return duration
# End get_duration()

# Just adds a minute
def add_duration(intime):
	intimeDatetime = datetime.strptime(intime,'%H:%M:%S')
	if intimeDatetime.minute == 59:
		return double_digits(str(intimeDatetime.hour+1)) + ':00:' + double_digits(str(intimeDatetime.second))
	else:	
		return double_digits(str(intimeDatetime.hour)) + ':' + double_digits(str(intimeDatetime.minute+1)) + ':' + double_digits(str(intimeDatetime.second))
# End add_duration()

# Comma-separated list of all accessible Google Spreadsheets
def get_alldocs(connection):
	docs = []
	for doc in connection.openall():
		docs.append(doc.title)
	return ', '.join(docs)
# End get_alldocs()

def main():
	# Change working directory to place of python script.
	os.chdir(os.path.dirname(os.path.abspath(__file__)))
	print '-------------------------------------------------------------------------------'
	print 'Welcome to clipgen v{1}, for use by Paradox User Research\n\nWorking directory: {0}\nPlace video files and the oauth.json file in this directory.'.format(os.getcwd(), VERSIONNUM)
	if DEBUGGING: print '! DEBUG Debug mode is ON. Several limitations apply and more things will be printed.'
	# Remember that documents need to be shared to the email found in the json-file for OAuth-ing to work.
	# Each user of this program should also have their own, unique json-file (generate this on the Google Developer API website).
	scope = ['https://spreadsheets.google.com/feeds',
	 		 'https://www.googleapis.com/auth/drive']
	try:
		credentials = ServiceAccountCredentials.from_json_keyfile_name('oauth.json', scope)
	except IOError as e:
		print '{0}\nCould not find credentials (oauth.json).'.format(e)
		# TODO
		# Here we could have an interactive method that asks the user for the right directory to work in. Same for video files (would require some new code)
		sys.exit(0)
	try:
		if DEBUGGING: print '\n! DEBUG Attempting login...'
		gc = gspread.authorize(credentials)
		if DEBUGGING: '! DEBUG Login successful!\n'
	except gspread.exceptions.GSpreadException as e:
		print '{0}\n! ERROR Could not authenticate.\n'.format(e)
		sys.exit(0)

	inputFileFails = 0

	while True:
		inputName = raw_input('\nPlease enter the index, name, URL or key of the spreadsheet (\'all\' for list, \'new\' for list of newest, \'last\' to immediately open latest, \'settings\' to change settings):\n>> ')
		try:
			if inputName[:4] == 'http':
				# In case user copies a URL, we can handle that.
				worksheet = gc.open_by_url(inputName).worksheet(SHEET_NAME)
				break
			elif inputName[:3] == 'all':
				# Lists all Sheets, prefixed by a number.
				docList = get_alldocs(gc).split(',')
				print '\nAvailable documents:'
				for i in range(len(docList)):
					print '{0}. {1}'.format(i+1, docList[i].strip())
			elif inputName[:3] == 'new':
				# Typing 'new' shows the three latest Sheets (handy in case we have dozens of Sheets later).
				docList = get_alldocs(gc).split(',')
				print '\nNewest documents:'
				for i in range(3):
					print '{0}. {1}'.format(i+1, docList[i].strip())
			elif inputName[:4] == 'last':
				# This is equivalent to opening the Sheet numbered 1 in the 'all' list.
				latest = get_alldocs(gc).split(',')[0]
				worksheet = gc.open(latest).worksheet(SHEET_NAME)
  				break
  			elif inputName[0].isdigit():
  				# If user enters a number, we open the Sheet of that number from the 'all' list.
  				i = int(inputName)-1
  				worksheet = gc.open(get_alldocs(gc).split(',')[i].strip()).worksheet(SHEET_NAME)
  				break
  			elif inputName[:8] == 'settings':
				# This mode allows users to change settings for this run of the program only
				set_program_settings()
			elif inputName.find(' ') == -1:
				# If user has entered text that has no spaces (and hasn't been caught as a number, per above) we try to open it as a GID key.
				worksheet = gc.open_by_key(inputName).worksheet(SHEET_NAME)
				break
			else:
				# As we have free text entry, we match it to a Sheet name (regardless of case) and then open that Sheet.
				inputName = inputName.strip().lower()
				docList = get_alldocs(gc).split(',')
				for i in range(len(docList)):
					if docList[i].strip().lower() == inputName:
						worksheet = gc.open(docList[i]).worksheet(SHEET_NAME)
				break
		except gspread.SpreadsheetNotFound:
			inputFileFails += 1
			if inputFileFails <= 1 or inputFileFails >= 3:
				print '\nDid not find spreadsheet. Please try again.'
			else:
				print '\n###############################################################################'
				print 'Remember that you need to share the spreadsheet you want to parse. Share it with the user listed in the json-file (value of client_email).'
				print '\nThis needs to be done on a per-document basis.'
				print '\nAvailable documents: {0}'.format(get_alldocs(gc))
				print '###############################################################################\n'
		# End try/except
	# End while

	print 'Connected to Google Drive!'
	inputModeFails = 0

	while True:
		while True:
			inputMode = raw_input('\nSelect mode: (b)atch, (r)ange, (c)ategory or (l)ine\n>> ')
			try:
				if inputMode[0] == 'b' or inputMode == 'batch':
					gc.login()
					timesList = generate_list(worksheet, 'batch')
					break
				elif inputMode[0] == 'l' or inputMode == 'line':
					gc.login()
					timesList = generate_list(worksheet, 'line')
					break
				elif inputMode[0] == 'r' or inputMode == 'range':
					gc.login()
					timesList = generate_list(worksheet, 'range')
					break
				elif inputMode[0] == 'c' or inputMode == 'cat' or inputMode == 'category':
					gc.login()
					timesList = generate_list(worksheet, 'category')
					break
				elif inputMode == 'positive':
					gc.login()
					timesList = generate_list(worksheet, 'batch', 'Positive')
					break
				#elif inputMode[0] == 's' or inputMode == 'select':
				#	gc.login()
				#	timesList = generate_list(worksheet, 'select')
				#	break
				elif inputMode == 'karl':
					plogo()
				elif inputMode == 'test':
					timesList = generate_list(worksheet, 'test')
					break
			except (IndexError, gspread.exceptions.GSpreadException) as e:
				inputModeFails += 1
				try:
					if DEBUGGING: print '! ERROR Message \'{0}\'\n! DEBUG Attempting reconnect\n'.format(e)
					gc.login()
				except gspread.AuthenticationError as e:
					print '{0}\nCould not authenticate.'.format(e)
					sys.exit(0)
			# End try/except
		# End while

		print '\n* ffmpeg is set to never prompt for input and will always overwrite.\n  Only warns if close to crashing.\n'
		videosGenerated = 0

		for i in range(0, len(timesList)):
			# timesList is a list containing issues, one per index
			# issues are dicts that hold:
			# - cell 			Full gspread Cell object (row, col, value)
			# - desc 			String, summary description of the issue
			# - study 			Unicode string, name of the study
			# - participant 	String, participant ID (without prefix)
			# - times 			List, contains one timestamp pair (as a tuple) per index
			# - category 		String, category heading found over issue
			# Note that the 'times' entry in the dict is generated during the clean_issue method call.

			timesList[i] = clean_issue(timesList[i])
			for j in range(0,len(timesList[i]['times'])):
				vidIn, vidOut = timesList[i]['times'][j]
				try:
					vidName = set_filename('[Study ' + filter(unicode.isdigit, timesList[i]['study']) + '][' + timesList[i]['category'] + '] ' + timesList[i]['desc'] + FILEFORMAT)
				except TypeError as e:
					print '! ERROR Some character encoding nonsense occured:\n  {0}'.format(e)
					break

				baseVideo = timesList[i]['study'] + '_' + timesList[i]['participant']  + FILEFORMAT
				
				completed = ffmpeg(inputfile=baseVideo, outputfile=vidName, startpos=vidIn, outpos=vidOut, reencode=REENCODING)
				if completed:
					videosGenerated += 1
		# End for

		if not REENCODING:
			print '* No re-encoding done, expect:\n- inaccurate start and end timings\n- lossy frames until first keyframe\n- bad timecodes at the end\n'
		else:
			pass
		print 'All done, created {0} videos!\nFiles are in {1}\n'.format(videosGenerated, os.getcwd())
		yn = raw_input('Continue working (y) or quit the program (n)? y/n\n>> ')
		if yn == 'n':
			break
		else:
			pass
	# End while
# End main()

def plogo():
	print '                                          ;.\n	                                  ###:   ######@.\n	                                  ;###   #########\n 	                          .###;    ###   #########@\n	                          +####\'   ###;  ##########\n	                           #####   @##@  ##########    .\n 	                     \'      #####  @###,\'#########@    #@\'\n	                    +##+     ##### ###############@   ######\n	                    +###;    \'#####################  #######\n 	                     ####     ##############################@\n	                      ####   \'###############################\'\n	                       ####.,################################@\n 	                ;#,    :#####################################\n	               @####;  :################,    .@############@\n	               #######@###############+         ###########\n 	                ;#####################           ##########    ,\n	                 :###################@           ###########+@###;\n	                 \'####################           +################\n 	                 \'########, ##########:          #################\'\n	                 #########  @##########      @#########@ #########:\n	                :#########  ;#########;     @##########  .####+.,\';\n 	                @#########+ ##########     \'##########+   @###\n	                \'######@#############      ###########    .###\'\n	                 ###@    \'#####@\'+#;      .###########     ####\'\n 	                :###       ###@            ###########     ######@\n	          ,##@::###@       @##+            @##########@\'   ########\n	          @#########,      ####\'           \'#######################\n 	          ###########;     #####@           #############+@#######@\n	          .###########     +###@##@         #@\'########+    ######,\n	           ###########       ## \'###        #\' #\'@#####     ,#####\n 	           ####\'@###,        ##  @##;      :#, #+ ####:      #####\n	           ###   ;##         ##   ##.      @#\' #@ ,###       @#####\n	           ##+    ##\' :     \'###  ##       ##  ##  @##       @#####@\n 	          .##@    #####.     +######,     \'##  @#   ##       @#####\'\n	           ###,  ######+      @###@##     +##  ,#.  :@       @#####\n	           @###########\'      @#@#\'.#     ###   #@           #####@\n 	           ,###########,      @\' #@       ###  ,##           #####\'\n	           .###@  #####       ,\' ,#       ####,###\'         +#####\'\n	            ##@   #####                   #########         ######\n 	            +\'   @####@                @######+   :        @######\'\n	               @######@              \'######@            ;#######;\n	             \'########@             @######             #########\n 	             \'#########            .@,#####             ########,\n	              @########.             :####.             #######@\n	               @#######@             @####              ######+\n 	                :#######             #. @@             ,###:\n	                  ######\'            \'  :@             ####,\n	                   #####\'                @            #####+\n 	                   #####\'                           \'######\'\n	                    ####:                         \'#######\' \n	                    ####                         #######@\n 	                    ####                        ,######:\n	                    ###:                     ,\',#####@\n	                   \'##@                    ,########:\n	                   @#@                   \'######  \' \n 	                                       \'@######\n	                                        @##@@.'
	print '\n	 /$$$$$$$                                    /$$\n 	| $$__  $$                                  | $$                    \n 	| $$  \ $$ /$$$$$$   /$$$$$$  /$$$$$$   /$$$$$$$  /$$$$$$  /$$   /$$\n 	| $$$$$$$/|____  $$ /$$__  $$|____  $$ /$$__  $$ /$$__  $$|  $$ /$$/\n 	| $$____/  /$$$$$$$| $$  \__/ /$$$$$$$| $$  | $$| $$  \ $$ \  $$$$/ \n 	| $$      /$$__  $$| $$      /$$__  $$| $$  | $$| $$  | $$  >$$  $$ \n 	| $$     |  $$$$$$$| $$     |  $$$$$$$|  $$$$$$$|  $$$$$$/ /$$/\  $$\n 	|__/      \_______/|__/      \_______/ \_______/ \______/ |__/  \__/'
# End plogo()

if __name__ == '__main__':
    try:
    	main()
    except KeyboardInterrupt:
    	print '\nInterrupted by user'
    	try:
    		sys.exit(0)
    	except SystemExit:
    		os._exit(0)
	# End try/except
# End __init__