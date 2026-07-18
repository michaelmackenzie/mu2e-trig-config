#!/usr/bin/env python

import json
import os

from argparse import ArgumentParser

from codecs import open


def capitalize(word):
    if not word:
        return word
    nLetters = 1
    nn = word[0].upper()
    return nn + word[nLetters:]


def generateLogger(
    evtMode,
    outdir,
    dictLog,
    logName,
    dictStreams,
    isOfflineBuild=False,
    doIt=True,
    verbose=False,
):
    name_app = ".fcl"
    if evtMode != "all":
        name_app = "_" + evtMode + ".fcl"

    loggerFileName = outdir + "/" + logName + name_app
    loggerConfigFileName = outdir + "/" + logName + "Config" + name_app

    # if isOfflineBuild == False:
    #     os.system("chmod 755 {}".format(loggerConfigFileName))
    #     os.system("chmod 755 {}".format(loggerFileName))
    if doIt == True:
        loggerMenu = open(loggerFileName, "w")
        loggerConfig = open(loggerConfigFileName, "w")

    tagName = capitalize(logName)

    if doIt == True:
        loggerConfig.write("BEGIN_PROLOG\n")
        loggerConfig.write(tagName + "Config: {\n")

    list_of_logger_streams = []
    # create the instances of the RootDAQOutput module
    if doIt == True:
        loggerConfig.write("    outputs : {\n")

    for k in dictLog:
        if dictLog[k]["enabled"] == 0:
            continue
        vv = k.split("_")
        streamName = "".join([capitalize(x) for x in vv]) + "Output"
        list_of_logger_streams.append(streamName)
        #
        if doIt == True:
            loggerConfig.write("         {}:".format(streamName) + " {\n")
            loggerConfig.write("            module_type: RootDAQOutput\n")
            loggerConfig.write(
                "            SelectEvents : {}\n".format(json.dumps(dictStreams[k]))
            )
            loggerConfig.write("            maxSubRuns   : 1\n")
            loggerConfig.write('            fileName     : "{}_%r_%#.art"\n'.format(k))
            loggerConfig.write("         }\n\n")
    if doIt == True:
        loggerConfig.write("    }\n\n")

    if (
        doIt == True
    ):  # TO-DO: need to add a sequence for running the analyzer module that provides the DAQ metrics
        loggerConfig.write("    analyzers : {\n")

    if doIt == True:
        loggerConfig.write("    }\n")
        loggerConfig.write("}\n")
        loggerConfig.write("END_PROLOG\n")
        loggerConfig.close()

    if doIt == True:
        loggerMenu.write("BEGIN_PROLOG\n")
        loggerMenu.write(tagName + "Outputs: {\n")
        loggerMenu.write("  outputs: [")
    for i in range(len(list_of_logger_streams)):
        k = list_of_logger_streams[i]
        if i != len(list_of_logger_streams) - 1:
            if doIt == True:
                loggerMenu.write("{},".format(k))
        else:
            if doIt == True:
                loggerMenu.write("{}".format(k))
    #
    if verbose == True:
        print(
            "[generateLogger] {} OUTPUT PATHS FOUND ({}): {}".format(
                logName, len(list_of_logger_streams), list_of_logger_streams
            )
        )
    if doIt == True:
        loggerMenu.write("]\n")
        loggerMenu.write("}\n")

        loggerMenu.write(tagName + "Menu: {\n")
        loggerMenu.write("  end_paths: [ outputs ] \n")
        loggerMenu.write("}\n")
        loggerMenu.write("END_PROLOG\n")
        loggerMenu.close()

    # if isOfflineBuild==False:
    #     os.system("chmod 444 {}".format(loggerConfigFileName))
    #     os.system("chmod 444 {}".format(loggerFileName))

    return [loggerFileName, loggerConfigFileName]


################################################################################
##
##
##
################################################################################
def generateMenu(
    evtMode,
    outdir,
    dictMenu,
    menuName,
    dictStreams,
    proc_name,
    isOfflineBuild,
    doIt=True,
    verbose=False,
):
    name_app = ".fcl"
    if evtMode != "all":
        name_app = "_" + evtMode + ".fcl"
    trigMenuFileName = outdir + "/" + menuName + name_app
    psConfigFileName = outdir + "/" + menuName + "PSConfig" + name_app

    # if isOfflineBuild==False:
    #     os.system("chmod 755 {}".format(trigMenuFileName))
    #     os.system("chmod 755 {}".format(psConfigFileName))

    if verbose == True:
        print("trigMenuFileName: {}".format(trigMenuFileName))
    if doIt == True:
        trigMenu = open(trigMenuFileName, "w")
        psConfig = open(psConfigFileName, "w")

    tag = capitalize(menuName)
    if doIt == True:
        trigMenu.write("BEGIN_PROLOG\n")
        trigMenu.write(tag + ": {\n")
        trigMenu.write("  trigger_paths: [\n")
        psConfig.write("BEGIN_PROLOG\n")
        psConfig.write(tag + "PSConfig: {\n")

    list_of_calo_trk_paths = []
    for k in dictMenu:
        if dictMenu[k]["enabled"] == 0:
            continue
        evtModes = dictMenu[k]["eventModeConfig"]
        evtModeCheck = evtMode == "all"
        for ll in range(len(evtModes)):
            if evtMode != "all" and evtMode == evtModes[ll]["eventMode"]:
                evtModeCheck = True
                break
        if evtModeCheck:
            list_of_calo_trk_paths.append(k)

    for i in range(len(list_of_calo_trk_paths)):
        path = list_of_calo_trk_paths[i]
        if doIt:
            if i != len(list_of_calo_trk_paths) - 1:
                trigMenu.write('     "{}:{}",\n'.format(dictMenu[path]["bit"], path))
            else:
                trigMenu.write('     "{}:{}"\n'.format(dictMenu[path]["bit"], path))
        #
        vv = path.split("_")
        streamName = "".join([capitalize(x) for x in vv])
        if doIt == True:
            psConfig.write("   {}PS:".format(streamName) + " {\n")
            psConfig.write("      module_type: PrescaleEvent\n")
            psConfig.write("      EventWindowMarker: ProcessCFOData\n")
        evtModes = dictMenu[path]["eventModeConfig"]
        psInput = "[ "
        notFirst = False
        for ll in range(len(evtModes)):
            if evtMode != "all" and evtMode != evtModes[ll]["eventMode"]:
                continue
            if notFirst:
                psInput += ","
            psInput += (
                " { eventMode: "
                + "{}".format(evtModes[ll]["eventMode"])
                + " prescale:{}".format(evtModes[ll]["prescale"])
                + "}"
            )
            notFirst = True
        psInput += " ]"

        if doIt == True:
            psConfig.write("      eventModeConfig : {}\n".format(psInput))
            psConfig.write("}\n\n")

        vv = dictMenu[path]["eventModeConfig"]
        for dd in vv:
            for s in dd["streams"]:
                if s not in dictStreams:
                    print(s, "not found in the dictionary")
                if path not in dictStreams[s]:
                    trg_path = proc_name + "*:" + path
                    dictStreams[s].append(trg_path)

    #
    if verbose == True:
        print(
            "[generateMenu] {} TRIGGER PATHS FOUND (): {}".format(
                menuName, len(list_of_calo_trk_paths), list_of_calo_trk_paths
            )
        )
    # Add a trigger list that doesn't include the trigger bit, for SelectEvents
    if doIt:
        trigMenu.write("  ]\n")
        trigMenu.write("  trigger_list: [\n")
        if "lumiStream" in list_of_calo_trk_paths: list_of_calo_trk_paths.remove("lumiStream") # FIXME
        for i in range(len(list_of_calo_trk_paths)):
            path = list_of_calo_trk_paths[i]
            trigMenu.write(f'     "{path}"')
            if i != len(list_of_calo_trk_paths) - 1:
                trigMenu.write(",")
            trigMenu.write("\n")

    #
    if doIt == True:
        psConfig.write("}\n")
        psConfig.write("END_PROLOG\n")
        psConfig.close()
        trigMenu.write("  ]\n")
        trigMenu.write("}\n")
        trigMenu.write("END_PROLOG\n")
        trigMenu.close()

    # if isOfflineBuild==False:
    #     os.system("chmod 444 {}".format(trigMenuFileName))
    #     os.system("chmod 444 {}".format(psConfigFileName))

    return [psConfigFileName, trigMenuFileName]


# --------------------------------------------------------------------------------
#    Function used to generate the Menu file in the Offline environemnt
#
#
# --------------------------------------------------------------------------------
def generateOffline(menuFile, evtMode, outdir, doIt=False, verbose=False):

    tag = menuFile.split("/")[-1].split(".")[0]

    if verbose:
        print("configFileText = ", menuFile)

    # when we run from SConscript to create the targets,
    # we are in the subdir.  When running in Offline scons, we are in Offline,
    # when in Muse, we are in Offline parent dir
    # This code makes this always run in the scons default dir, either
    # Offline or its parent dir
    srcDir = ""
    outDir = ""
    owd = os.getcwd()
    if verbose:
        print("start owd= ", owd)
    if "MUSE_WORK_DIR" in os.environ:
        # then we are running in Muse, make adjustments
        if verbose:
            print("running in Muse mode ")
        os.chdir(os.environ["MUSE_WORK_DIR"])
        srcDir = "mu2e-trig-config/"
        # like "build/sl7-prof-e20/Offline/"
        outDir = os.environ["MUSE_BUILD_BASE"] + "/mu2e-trig-config/"
    else:
        # when we run from SConscript, the owd is the python subdir
        # but all file name are relative to Offline, so go there
        words = owd.split("/")
        if words[-1] == "python":
            os.chdir("../..")
        # accept empty default srcDir and outDir, so build in Offline

    tempArr = menuFile.split("/")
    tempArr = tempArr[-1].split(".")
    configFileBaseName = tempArr[0]
    configFileName = srcDir + "data/" + configFileBaseName + ".json"

    if verbose:
        print("owd = ", owd)
        print("pwd = ", os.getcwd())
        print("srcDir = ", srcDir)
        print("outDir = ", outDir)

    sourceFiles = []
    targetFiles = []

    sourceFiles.append(configFileName)

    data_files = [srcDir + "data/physMenu.json", srcDir + "data/extrPosMenu.json"]
    for fn in data_files:
        sourceFiles.append(fn)

    trig_prolog_files = [
        srcDir + "core/trigDigiInputsEpilog.fcl",
        srcDir + "core/trigFilters.fcl",
        srcDir + "core/trigProducers.fcl",
        srcDir + "core/trigSequences.fcl",
        srcDir + "core/trigServices.fcl",
    ]
    for fn in trig_prolog_files:
        sourceFiles.append(fn)

    relProjectDir = "gen"
    projectDir = outDir + relProjectDir
    os.system("mkdir -p {}".format(projectDir))

    with open(menuFile) as f:
        conf = json.load(f)
        keys = conf.keys()
        if verbose == True:
            print("[generateMenuJSON] KEYS FOUND: {}".format(keys))
        data_streams = {}
        for k in conf["dataLogger_streams"]:
            data_streams[k] = []

        dict_trkcal_triggers = conf["trigger_paths"]
        trkcal_proc_name = conf["trkcal_filter_process_name"]
        targetFiles += generateMenu(
            evtMode,
            projectDir,
            dict_trkcal_triggers,
            "trig_" + tag,
            data_streams,
            trkcal_proc_name,
            True,
            doIt,
            verbose,
        )
        if verbose == True:
            print("[generateMenuJSON] DATA STREAMS FOUND: {}".format(data_streams))

        dict_agg_triggers = conf["agg_trigger_paths"]
        add_proc_name = conf["crv_agg_process_name"]
        targetFiles += generateMenu(
            evtMode,
            projectDir,
            dict_agg_triggers,
            "agg_" + tag,
            data_streams,
            add_proc_name,
            True,
            doIt,
            verbose,
        )

        # now produce the logger menus
        dict_logger = conf["dataLogger_streams"]
        targetFiles += generateLogger(
            evtMode,
            projectDir,
            dict_logger,
            "trigLogger_" + tag,
            data_streams,
            True,
            doIt,
            verbose,
        )
        #
        dict_logger = conf["lumiLogger_streams"]
        lumi_streams = {}
        lumi_streams["lumi"] = []
        targetFiles += generateLogger(
            evtMode,
            projectDir,
            dict_logger,
            "trigLumiLogger_" + tag,
            lumi_streams,
            True,
            doIt,
            verbose,
        )

    return (
        sourceFiles,
        targetFiles,
        "python " + srcDir + "python/generateMenuFromJSON.py",
    )

    # psConfig.write("}\n")
    # psConfig.close()
    # trigMenu.write("  ]\n")
    # trigMenu.write("}\n")
    # trigMenu.close()

    # os.system("chmod 444 {}".format(trigMenuFileName))
    # os.system("chmod 444 {}".format(psConfigFileName))


# --------------------------------------------------------------------------------
#    Function used to generate the Menu file in the Online environment
#
#
# --------------------------------------------------------------------------------
def generate(menuFile, evtMode, outdir, verbose):
    tag = menuFile.split("/")[-1].split(".")[0]

    with open(menuFile) as f:
        conf = json.load(f)
        keys = conf.keys()
        if verbose == True:
            print("[generateMenuJSON] KEYS FOUND: {}".format(keys))
        data_streams = {}
        for k in conf["dataLogger_streams"]:
            data_streams[k] = []

        dict_trkcal_triggers = conf["trigger_paths"]
        trkcal_proc_name = conf["trkcal_filter_process_name"]
        generateMenu(
            evtMode,
            outdir,
            dict_trkcal_triggers,
            "trig_" + tag,
            data_streams,
            trkcal_proc_name,
            False,
            True,
            verbose,
        )
        if verbose == True:
            print("[generateMenuJSON] DATA STREAMS FOUND: {}".format(data_streams))

        dict_agg_triggers = conf["agg_trigger_paths"]
        add_proc_name = conf["crv_agg_process_name"]
        generateMenu(
            evtMode,
            outdir,
            dict_agg_triggers,
            "agg_" + tag,
            data_streams,
            add_proc_name,
            False,
            True,
            verbose,
        )

        # now produce the logger menus
        dict_logger = conf["dataLogger_streams"]
        generateLogger(
            evtMode,
            outdir,
            dict_logger,
            "trigLogger_" + tag,
            data_streams,
            False,
            True,
            verbose,
        )
        #
        dict_logger = conf["lumiLogger_streams"]
        lumi_streams = {}
        lumi_streams["lumi"] = []
        generateLogger(
            evtMode,
            outdir,
            dict_logger,
            "trigLumiLogger_" + tag,
            lumi_streams,
            False,
            True,
            verbose,
        )

    # psConfig.write("}\n")
    # psConfig.close()
    # trigMenu.write("  ]\n")
    # trigMenu.write("}\n")
    # trigMenu.close()

    # os.system("chmod 444 {}".format(trigMenuFileName))
    # os.system("chmod 444 {}".format(psConfigFileName))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-mf",
        "--menu-file",
        dest="menuFile",
        default="data/physMenu.json",
        help="Input Menu file",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_false",
        dest="verbose",
        default=True,
        help="don't print status messages to stdout",
    )
    parser.add_argument(
        "-o", "--outdir", dest="outdir", default="gen", help="Outout directory"
    )
    parser.add_argument(
        "-evtMode",
        "--event-mode",
        dest="evtMode",
        default="all",
        help="Specify a single event mode if you want a single-event-mode Menu: OnSpill, OffSpill. The default is 'all'",
    )

    args = parser.parse_args()

    os.system("mkdir -p {}".format(args.outdir))

    # check the event mode
    allowed_evtModes = ["OnSpill", "OffSpill", "all"]
    if args.evtMode not in allowed_evtModes:
        print(
            "[generateMenuFromJSON] EVENT-MODE {} NOT ALLOWED! THE POSSIBLE OPTIONS ARE: {}".format(
                args.evtMode, allowed_evtModes
            )
        )
        exit(1)

    generate(args.menuFile, args.evtMode, args.outdir, args.verbose)
