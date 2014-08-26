#!/usr/local/bin/python3

import sys
import getopt
import os
import subprocess
import signal as sg
import sys


def signalHandler(signal,frame):
  if (shell.activePid > 0):
    os.kill(shell.activePid,sg.SIGSTOP)
    sys.stdout.write("\nStopped: " + str(shell.activePid) + "\n")
    shell.addJob(shell.activeCommand,shell.activePid)

class Shell:
  def __init__(self):
    self.dir_ = os.getcwd()
    self.systemCommands = ['cd','pwd','h','history','jobs']
    self.history = []
    self.jobs = []
    self.activePid = 0
    self.activeCommand =0

  def getCurrentDirectory(self):
    return self.dir_

  def updateCurrentDirectory(self):
    self.dir_ = os.getcwd()

  def changeDirectory(self,relPath):
    os.chdir(relPath)
    self.updateCurrentDirectory()

  def showHistory(self):
    for i in range(len(self.history)-10,len(self.history)):
      if (i >= 0):
        sys.stdout.write(str(i+1) + ": " + str(self.history[i]) + "\n")

  def isSystemCommand(self,command,index):
    return command.commands[index].split(" ")[0] in self.systemCommands

  def execSystemCommand(self,command,index):
    #split command and args
    args = command.commands[index].split(" ")[1:]
    command = command.commands[index].split(" ")[0]
    if command == 'cd':
      try:
        self.changeDirectory(" ".join(args))
      except OSError as e:
        sys.stdout.write(str(e)+"\n")
    elif command =='pwd':
      sys.stdout.write(self.getCurrentDirectory() + '\n')
    elif command == 'h' or command == 'history':
      if (len(args) == 0):
        self.showHistory()
      elif (len(args) == 1):
        commandID = int(args[0])-1

        if (len(self.history) <= commandID or commandID < 0):
          print ("Error, Invalid History ID")
        else:
          #remove last item from history, we only want the history for the command the history is referencing
          #could get infinte loops as a result?
          del self.history[-1]
          #execute command
          historyCommand = self.history[commandID]
          self.execCommand(historyCommand)
      else:
        #print an error
        print("Usage: history itemNumber")
    elif command == 'jobs':
      for job in self.jobs:
        sys.stdout.write(str(job[0]) + " " + str(job[1]) +" " + str(job[2])+"\n")
    sys.exit(0)

  def isGrounding(self,command):
    return command.commands[0].split(" ")[0] in ['fg','bg']

  def doGrounding(self,command):
    args = command.commands[0].split(" ")[1:]
    command = command.commands[0].split(" ")[0]
    if command == 'fg':
      if (len(args) == 0):
        job = self.jobs[0]
      else:
        job = self.jobs[int(args[0])-1]
      os.kill(job[0],sg.SIGCONT)
      os.waitpid(job[0],0)
    elif command == 'bg':
      if (len(args) == 0):
        job = self.jobs[0]
      else:
        job = self.jobs[int(args[0])-1]
      os.kill(job[0],sg.SIGCONT)

  def translateJobStatus(self,status):
    if ("S" in status):
      status = "Sleeping"
    elif("R" in status):
      status = "Running"
    elif("T" in status):
      status = "Stopped"
    return status

  def addJob(self,command,pid):
    status = self.getJob(pid)
    self.jobs.append([pid,self.translateJobStatus(status),command])
    return len(self.jobs)

  def updateJobs(self):
    #Remove jobs that have finished
    for job in self.jobs:
      try:
        job[1] = self.getJob(job[0])
      except subprocess.CalledProcessError:
        self.jobs.pop(self.jobs.index(job))
        continue #yeah....
      job[1] = self.translateJobStatus(job[1])
      if (job[1] is None):
        self.jobs.pop(self.jobs.index(job))
      elif("Z" in str(job[1])):
        os.waitpid(job[0],0)
        #print out the fact that the job is done
        sys.stdout.write("["+str(self.jobs.index(job)+1)+"]"+"\tDone"+"\t "+ job[2].commandStr+"\n")
        self.jobs.pop(self.jobs.index(job))



  def getJob(self,pid):
    out = subprocess.check_output(["ps",str(pid)])
    return (str(out).split("\\n")[1].split(" ")[3])

  def execCommand(self,command):
    #check to see if the command has an ampersand, by looking at the last argument
    useAmpersand = command.hasAmpersand

    self.history.append(command)

    #must handle fg / bg before forking!
    if self.isGrounding(command):
      self.doGrounding(command)
    else:
      pid = os.fork()
      if (pid == 0):
        if (command.doPiping()):
          i = len(command.commands)-1
          while i > 0:
            read,write = os.pipe()
            #do piping here, should be a loop eventually
            if (os.fork() == 0):
              #print ([commands[0].split(" ")[0],commands[0].split(" ")[1:]])
              os.dup2(write,sys.stdout.fileno())
              os.close(read)
              i-= 1
            else:
              os.dup2(read,sys.stdin.fileno())
              os.close(write)
              #should wait here if ampersand
              if (not useAmpersand):
                os.wait()
              break
          if (self.isSystemCommand(command,i)):
            self.execSystemCommand(command,i)
          else:
            command.execute(i)
        else:
          #We are in the child, execute
          if self.isSystemCommand(command,0):
            self.execSystemCommand(command,0)
          else:
            command.execute(0)
      else:
        if (useAmpersand):
          #print process id and continue
          jobid = self.addJob(command,pid)
          print ("[" + str(jobid) + "]" + " " + str(pid))
        else:
          #We are in the parent, continue
          self.activePid = pid
          self.activeCommand = command
          try:
            os.waitpid(pid,0)
          except InterruptedError:
            pass #?
          self.activeCommand = 0
          self.activePid = 0

class ShellCommand:
  def __init__(self,command):
    self.commandStr = command.rstrip("\n ")
    self.commands = self.removePipe()
    self.removeAmpersand()

  def __str__(self):
    return self.commandStr

  def doPiping(self):
    return '|' in self.commandStr

  def removePipe(self):
    commands = self.commandStr.split("|")
    for i in range(len(commands)):
      commands[i] = commands[i].strip(" ")
    return commands

  def removeAmpersand(self):
    if "&" in self.commandStr:
      self.hasAmpersand = True
      self.commands[-1] = self.commands[-1].rstrip("& ")
    else:
      self.hasAmpersand = False

  def execute(self,index):
    command = self.commands[index].split(" ")[0]
    args = self.commands[index].split(" ")[1:]
    args.insert(0,"")
    try:
      os.execvp(command,args)
    except FileNotFoundError:
      sys.stdout.write("Command Not Found: " + command + "\n")
      sys.exit(0)


shell = Shell()



def main():
  sg.signal(sg.SIGTSTP,signalHandler)
  while(True):
    #get current folder we are working in
    currentDirectory = shell.getCurrentDirectory().split("/")[-1]

    #check to see if there are any completed jobs
    shell.updateJobs()

    #write prompt
    sys.stdout.write("psh "+currentDirectory+"> ")
    sys.stdout.flush()
    #Read a line from standard input
    input = ShellCommand(sys.stdin.readline())
    if (input.commandStr != ""):
      shell.execCommand(input)


if __name__ == "__main__":
    main()
