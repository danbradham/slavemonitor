from System.Diagnostics import *
from System.IO import *
import System
from System import TimeSpan, DateTime

from Deadline.Events import *
from Deadline.Scripting import *
from Deadline.Slaves import *

import sys
import os
import textwrap


def GetDeadlineEventListener():
    return SlaveMonitor()


def CleanupDeadlineEventListener(eventListener):
    eventListener.Cleanup()


class SlaveMonitor(DeadlineEventListener):

    def __init__(self):
        self.OnJobErrorCallback += self.OnJobError

    def Cleanup(self):
        del self.OnJobErrorCallback

    def OnJobError(self, job, task, report):

        # Get slavemonitor config entries
        catch_nonzero = self.GetBooleanConfigEntry('CatchNonZero')
        nonzero_action = self.GetConfigEntry('NonZeroAction')
        use_error_threshold = self.GetBooleanConfigEntry('UseErrorThreshold')
        error_threshold = self.GetIntegerConfigEntry('ErrorThreshold')
        error_threshold_action = self.GetConfigEntry('ErrorThresholdAction')

        message = report.ReportMessage
        is_nonzero_message = 'non-zero error code -1073740777' in message

        if catch_nonzero and is_nonzero_message:
            try:
                fn = getattr(self, nonzero_action)
                fn(job, task, slave)
            except Exception as e:
                log(e)

        slave = report.ReportSlaveName
        job_error_reports = self.get_slave_reports_since_startup(slave, job)
        threshold_reached = len(job_error_reports) > error_threshold

        if use_error_threshold and threshold_reached:
            log('{} hit error threshold for job {}'.format(slave, job.JobName))
            try:
                fn = getattr(self, error_threshold_action)
                fn(job, task, slave)
            except Exception as e:
                log(e)

    def blacklist(self, job, task, slave):
        log('Blacklisting {} for {}'.format(slave, job))

        RepositoryUtils.AddSlavesToMachineLimitList(
            job.JobId,
            [slave]
        )

    def get_slave_reports_since_startup(self, slave, job):
        slave_info = RepositoryUtils.GetSlaveInfo(slave, True)
        slave_run_time = slave_info.SlaveRunningTime
        slave_reports = RepositoryUtils.GetSlaveReports(slave)
        error_reports = slave_reports.GetErrorReports()
        job_error_reports = []

        slave_start_time = DateTime.get_Now().AddSeconds(-slave_run_time)

        for report in error_reports:

            # Report time doesn't match local time zone
            # This is obviously fucked...add 85 minutes to the reported time
            # TODO: resolve this time offset nonsense

            report_time = report.ReportDateTimeOf
            if report.ReportJobName == job.JobName:
                if DateTime.op_GreaterThan(slave_start_time, report_time):
                    continue
                job_error_reports.append(report)

        return job_error_reports

    def relaunch_slave(self, job, task, slave):
        log('Restarting {} for {}'.format(slave, job))

        SlaveUtils.SendRemoteCommandNoWait(
            task.TaskSlaveMachineName,
            'ForceRelaunchSlave',
        )

    def restart_machine(self, job, task, slave):
        log('Restarting {} for {}'.format(slave, job))

        SlaveUtils.SendRemoteCommandNoWait(
            task.TaskSlaveMachineName,
            'OnLastTaskComplete RestartMachine',
        )

def log(msg):
    msg = textwrap.fill(
        'SLAVEMONITOR: {}'.format(msg),
        initial_indent='',
        subsequent_indent='    '
    )
    ClientUtils.LogText(msg)
