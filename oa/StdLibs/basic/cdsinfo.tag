##########################################################################
# cdsinfo.tag - Copyright (C) 1999 Cadence Design Systems, Inc.
#			All Rights Reserved.
#
# Setting entries in this file makes them effective for this directory and
# any subdirectories which do not in turn have cdsinfo.tag files in them.
##########################################################################

CDSLIBRARY

# CDSLIBCHECK - uncomment this to require that all libraries must have a
# cdsinfo.tag file with a CDSLIBRARY entry. Legal values are ON and OFF.
# By default (OFF), any directory listed in a cds.lib file is a library.
#
# CDSLIBCHECK OFF

# DMTYPE - uncomment this to define the DM system for Cadence's Generic
# DM facility. Values will be shifted to lower case. A value of 'none'
# implies that the data will never be managed.
#
DMTYPE none

# NAMESPACE - uncomment this to define the library namespace according
# to the type of machine on which the data resides. Legal values are
# `LibraryNT' and `LibraryUnix'.
#
NAMESPACE LibraryUnix
