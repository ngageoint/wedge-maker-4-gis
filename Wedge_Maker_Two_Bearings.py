#!/usr/bin/env python
# Python 2.7.5

"""TITLE: Wedge Maker for ArcGIS

DATE: 18 April 2016

SYNOPSIS: This tool allows the user to take a projected point feature class
and use it to create wedge and arcband shapes.  The tool outputs a polygon
feature class containing the wedges and arcbands.

REQUIREMENTS: This tool requires ArcGIS 10.1 or later and the ArcGIS Advanced
license level.

USAGE: This tool allows the user to take a projected point feature class and
use it to create wedge and arcband shapes.  An arcband shape is a wedge with
a portion of the wedge from the center point of the wedge to a specified
distance erased.  The point feature class's attribute table must have two
numeric fields for the two lines of bearing that define the start and end
of each wedge.  The point feature class must also have a field that defines
the radius of each wedge.  Optionally, it can have a field that defines the
inner radius of each arcband.  The tool outputs a polygon feature class
containing the wedges and arcbands.

The required fields are two numeric fields representing the two lines of
bearing for each wedge in decimal degrees.  The required outer (or only)
radius field and optional inner radius field must be text fields that are
formatted to work with the ArcGIS Buffer tool.  They must be in the format
"5 MILES" or "20 kilometers" or "8.33 NauticalMiles" (note that for multi-
word units of distance the unit of distance must not have a space between
the words.)  Every entry must include the units of distance.  If the
user does not specify an inner radius field, the output will not contain
any arcbands.  If the user does specify an inner radius field, any blank
entries in the inner radius field will be ignored and those features will
produce wedges instead of arcbands.

INPUT: This tool takes as its input a projected point feature class with
specific attributes defining the characteristics of the desired wedges/
arcbands.

OUTPUT: This tool outputs a polygon feature class.  Each feature is a wedge
or arcband as specified by the user's input.

METHODOLOGY: The tool reads the input points and extracts their coordinates.
It verifies that the required input fields exist and that the entries are
in the proper format.  It also verifies the optional inner radius field if
the user includes it.  The tool then creates a nested list of all of the
attributes of each wedge and processes it.  For each wedge, the tool
buffers the point by the outer radius and then creates a triangle emanating
from the point.  The triangle is then used to clip or erase from the circle
as appropriate.  If the angle between the two lines of bearing is between
135 and 225 degrees, the tool creates two smaller wedges and dissolves them
together because angles close to 180 degrees require extremely large
triangles, and the math may produce invalid coordinates.  In particular,
the triangle method fails completely with a 180-degree wedge.

For each wedge, the tool then checks whether the user wanted an arcband.
If so, the tool re-buffers the point by the inner radius and uses this
new, smaller circle to erase from the wedge.  The tool combines all of the
wedges into a single feature class and performs a table join from the
original feature class to carry over the attributes.

The tool assumes that when the user's lines of bearing are identical,
no wedge should be created at all, but when the user's lines of bearing
differ by an exact multiple of 360 degrees that a circle should be
created.

NOTES: The input point feature class MUST BE PROJECTED.  The tool requires
projected inputs because attempting to perform distance measurements with
unprojected data can lead to erroneous measurements.  The tool attempts to
detect unprojected input data and halt operation, but if the user manages to
disable or circumvent these checks, there is no guarantee that the measurements
will be accurate.

For purposes of this tool, due North is 0 degrees bearing and bearing
increases in a clockwise direction.  The tool is able to process negative lines
of bearing.

If the user specifies that a wedge have the exact same start and end lines of
bearing e.g. the user specifies "120" as the start and end line of bearing, the
tool detects this case and skips that wedge as a 0-degree wedge.  If the user
specifies start and end lines of bearing that differ by a multiple of 360
degrees e.g. the user specifies "120" and "480" or "-30" and "690" as the lines
of bearing, then the tool will create a full circle shape.
"""

import arcinfo, arcpy, traceback, math, os, sys


def printMessage(strMessage, messageType=0):

    """This function lets the user output a message to the ArcGIS geoprocessing
    results window with the severity level indicated by the messageType
    parameter or to the Python shell, depending upon in which environment the
    script is being run.
    """

    try:
        print(strMessage)
        if messageType == 0:
            arcpy.AddMessage(strMessage)
        elif messageType == 1:
            arcpy.AddWarning(strMessage)
        elif messageType == 2:
            arcpy.AddError(strMessage)

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))


def createOneWedge(centerX, centerY, r, firstAngle,
                   secondAngle, outWedgeName, projOut):

    """createOneWedge creates a single wedge feature class based upon input
    parameters.  It performs trigonometric calculations to determine the
    vertices of the Clip/Erase triangle, creates the circle and triangle
    geometry, and performs the necessary Clip/Erase to generate the wedge/
    Pac-Man shape.  Returns a string with the location of the output wedge.

    Keyword arguments:
    centerX -- The X coordinate of the center of the wedge (int or float)
    centerY -- The Y coordinate of the center of the wedge (int or float)
    r       -- The outer radius of the wedge (int or float)
    firstAngle -- The line of bearing of the start angle of the wedge (int or
    float)
    secondAnge -- The line of bearing of the end angle of the wedge (int or
    float)
    outWedgeName -- The path and name of the wedge to be created (string)
    projOut      -- The projection of the wedge to be created
    (arcpy.SpatialReference)

    firstAngle and secondAngle must fall in the range [0, 360).  r must be
    greater than 0 and must be in meters.
    """

    try:
        #theta is the angle between the two lines of bearing.  It will be used
        #in #calculations and to determine whether to intersect the circle
        #with the triangle or to clip the circle with the triangle.
        theta = secondAngle - firstAngle

        #If theta is less than 180 degrees, we'll use the triangle we're
        #creating to clip the circle and create our wedge.  If theta is
        #greater than 180 degrees, we'll use the triangle we're creating
        #to erase from the circle, keeping the larger "Pac-Man" shape
        #that remains.  In this particular script, if the user's inputted
        #theta is between 135 degrees and 225 degrees, the script instead
        #calls this createOneWedge function twice and forms two adjacent
        #smaller wedges for merging and dissolving.  The reason is that
        #the clip triangle becomes too large when the wedge angle is
        #too close to 180 degrees.
        if theta % 360 > 180:
            booEraseWedge = True
        else:
            booEraseWedge = False

        
        #Now switch to radians because Python's trigonometric functions
        #operate on radians instead of degrees.
        firstAngle = math.radians(firstAngle)
        secondAngle = math.radians(secondAngle)
        theta = math.radians(theta)

        #Explanation of "hyp" variable: Imagine a circle and the two lines
        #of bearing extending out from the circle center.  The angle between
        #these two lines is theta, as mentioned above.  Bisect theta with the
        #radius of the circle that falls exactly halfway between the two lines
        #of bearing.  Now draw the infinite line that is tangent to the circle
        #at the point where it intersects the circle radius that bisects theta.
        #Extend either line of bearing until it intersects this infinite line.

        #The triangle formed by the circle radius, the infinite tangent line,
        #and the extended line of bearing (as described above) is a right
        #triangle with the right angle being between the circle radius and the
        #infinite tangent line.  The hypotenuse is the extended line of bearing.
        #The other known angle of this triangle is the angle between the circle
        #radius and the extended line of bearing.  This angle is theta/2 because
        #the radius bisects the angle theta.  The radius is the known length of
        #the triangle because it's just a radius of the circle.

        #The equation below uses the known values "r" and "theta" and the cosine
        #function to calculate the length of that hypotenuse, the distance from
        #the center of the circle to the end of the extended line of bearing.
        hyp = math.fabs(r / math.cos(theta/2))

        #Using right triangle trigonometry, the code below calculates the X and
        #Y coordinates of the endpoint of the hypotenuse mentioned above.  The
        #radius that bisects theta creates two right triangles, one on each
        #side.  Therefore, the code below calculates the endpoint of the two
        #hypotenuses of those two triangles.  These two endpoints and the circle
        #center point form the triangle which we will use in either a clip or an
        #erase function later to form the desired wedge.
        ptAX = centerX + math.fabs(hyp) * math.sin(firstAngle)
        ptAY = centerY + math.fabs(hyp) * math.cos(firstAngle)
        ptBX = centerX + math.fabs(hyp) * math.sin(secondAngle)
        ptBY = centerY + math.fabs(hyp) * math.cos(secondAngle)

        #Now create the clip/erase triangle from its points        
        pt = arcpy.Point()

        #The array object will hold the circle center point and the two
        #triangle end points.  It will be used to create the triangle
        #shapefile.        
        array = arcpy.Array()

        #Build the first vertex of the clip/erase triangle from the center point
        #of the wedge
        pt.X = centerX
        pt.Y = centerY

        #Create a pointGeometry out of the arcpy.Point object, then add the
        #pointGeometry object to the list that will be used in the
        #CopyFeatures_management geoprocessor tool below.
        pointGeometry = arcpy.PointGeometry(pt, projOut)

        #Make a list with the center point in order to create a feature class
        #with just this one point.  This feature class will be buffered later
        #to create the circle.      
        centerList = []
        centerList.append(pointGeometry)

        #Add the circle center point and the other triangle points to the array
        #and then add it to the triangleList for use in the
        #CopyFeatures_management tool below.
        array.add(pt)

        #Add the two other clip/erase triangle vertices to array
        pt.X = ptAX
        pt.Y = ptAY
        array.add(pt)
        pt.X = ptBX
        pt.Y = ptBY
        array.add(pt)
        
        #Close the clip/erase triangle by adding the first vertex to the end of
        #the array
        array.add(array.getObject(0))

        #Make a Polygon object out of the array of point objects, then add it to
        #a list so that the list can be used in the geoprocessing tools below
        polygon = arcpy.Polygon(array, projOut)
        triangleList = []
        triangleList.append(polygon)

        #Buffer the center points by the correct distances
        circle = "in_memory\\circle"
        arcpy.Buffer_analysis(centerList, circle, str(r) + ' METERS')

        #If theta is greater than 180 degrees, erase the triangle from the
        #circle to get a Pac-Man shape.  If not, clip the circle with the
        #triangle and get the wedge shape.

        #In the special case where theta is a multiple of 360 (and greater than
        #0) don't do any erasing or clipping.  Just copy the circle feature over
        #to the final output feature class.

        outWedge = "in_memory\\" + outWedgeName

        if (secondAngle - firstAngle) % 360 != 0:
            if booEraseWedge == True:
                arcpy.Erase_analysis(circle, triangleList, outWedge, "")
            else:
                arcpy.Clip_analysis(circle, triangleList, outWedge, "")
        else:
            arcpy.CopyFeatures_management(circle, outWedge)

        #Remove the BUFF_DIST field from outWedge
        arcpy.DeleteField_management(outWedge, 'BUFF_DIST')

        arcpy.Delete_management(circle)
        del triangleList
        
        #Return the string containing the location and name of the output wedge
        return outWedge

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))
        

def parseRadius(textRadius, sInputUnits):

    """parseRadius checks whether the radius information (distance and units)
    has been properly entered into the attribute table.  It splits the input
    text and checks whether there are two parts (presumably the distance and the
    units.)  If successful, it then checks whether the distance part is
    actually a number and then whether the units part matches standard ESRI
    formatting because this radius information will be used as direct input
    into subsequent ArcGIS Buffer tool commands.  If any of the checks fail,
    the procedure returns a "None" value.

    Keyword arguments:
    textRadius  -- A distance in the format "X UNITS", where X is a real number
    and UNITS is one of these unit types: "CENTIMETERS", "DECIMETERS", "FEET",
    "INCHES", "KILOMETERS", "METERS", "MILES", "MILLIMETERS", "NAUTICALMILES",
    "YARDS" (string)
    sInputUnits -- A string indicating the units from which to convert the
    length found in textRadius (string)
    """

    try:
        radiusParts = textRadius.split()

        #We need two parts to the radius: the number and the units
        if len(radiusParts) != 2:
            return None

        #Make sure we have all digits or a single decimal point in the number
        #part
        foundDecimalPoint = False

        for digit in radiusParts[0]:
            #If we find a decimal point, make sure we don't have more than one
            if digit == ".":
                if foundDecimalPoint == False:
                    foundDecimalPoint = True
                else:
                    return None
            elif digit.isdigit() == False:
                return None

        #Make sure the units are all valid and spelled correctly
        if str(radiusParts[1]).upper() not in ["CENTIMETERS","DECIMETERS",
                                               "FEET","INCHES","KILOMETERS",
                                               "METERS","MILES","MILLIMETERS",
                                               "NAUTICALMILES","YARDS"]:
            return None

        #If the radius entry is valid, convert it to meters because subsequent
        #calculations will be done in meters
        if str(radiusParts[1]).upper() == "CENTIMETERS":
            radius = float(radiusParts[0])*0.01
        elif str(radiusParts[1]).upper() == "DECIMETERS":
            radius = float(radiusParts[0])*0.1
        elif str(radiusParts[1]).upper() == "FEET":
            radius = float(radiusParts[0])*0.3048
        elif str(radiusParts[1]).upper() == "INCHES":
            radius = float(radiusParts[0])*0.0254
        elif str(radiusParts[1]).upper() == "KILOMETERS":
            radius = float(radiusParts[0])*1000
        elif str(radiusParts[1]).upper() == "METERS":
            radius = float(radiusParts[0])*1
        elif str(radiusParts[1]).upper() == "MILES":
            radius = float(radiusParts[0])*1609.344
        elif str(radiusParts[1]).upper() == "MILLIMETERS":
            radius = float(radiusParts[0])*.001
        elif str(radiusParts[1]).upper() == "NAUTICALMILES":
            radius = float(radiusParts[0])*1852
        elif str(radiusParts[1]).upper() == "YARDS":
            radius = float(radiusParts[0])*0.9144
        elif sInputUnits == 'Foot_US':
            radius = float(radius)*3.2808399

        return radius

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))
        

def innerWedgeErase(centerX, centerY, r2, wedge, projOut):

    """Cut out the inner part of the wedge based upon the original point feature
    class's radius2 field.  Returns a string with the location of the output
    wedge.

    Keyword arguments:
    centerX -- The X coordinate of the center of the wedge (int or float)
    centerY -- The Y coordinate of the center of the wedge (int or float)
    r2      -- The inner radius of the wedge (int or float)
    wedge   -- A string specifying the location of the wedge feature class or
    object from which to erase (string)
    projOut      -- The projection of the wedge (arcpy.SpatialReference)

    r2 must be greater than 0 and must be in meters.
    """
    
    try:

        #Create an arcpy.Point() object that will be buffered        
        pt = arcpy.Point()
        pt.X = centerX
        pt.Y = centerY

        #Create a pointGeometry out of the arcpy.Point object, then add the
        #pointGeometry object to the list that will be used in the
        #CopyFeatures_management geoprocessor tool below.
        pointGeometry = arcpy.PointGeometry(pt,projOut)

        # Make a list with the center point in order to create a feature class
        # with just this one point.  This feature class will be buffered later
        # to create the circle.
        centerList = []
        centerList.append(pointGeometry)

        #Buffer the wedge center by the inner radius distance, then use that
        #buffer to erase from the input wedge
        circle = "in_memory\\circle"
        arcpy.Buffer_analysis(centerList, circle, str(r2) + ' METERS')
        oWedge2 = "in_memory\\oWedge2"
        arcpy.Erase_analysis(wedge, circle, oWedge2)
        arcpy.Delete_management(circle)
        del centerList
        arcpy.Delete_management(wedge)
        return oWedge2

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))


def createWedges(attributesList, inputFC, outputFC, outProj):

    """Create a feature class of wedge/arcband shapes based upon the attribute
    information in attributesList.

    #attributesList contains a list item for each wedge to be created, read from
    #the geometry and attributes of the input shapefile.  The order of the items
    #in the list is centerX, centerY, the first angle (angleA), the second angle
    #(angleB), the outer (or only) radius, the inner radius (optional), and a
    #number that counts the wedges as they are made.

    #The procedure passes the necessary information for each wedge onto the
    #createOneWedge procedure unless the wedge is between 135 and 225 degrees,
    #in which case it calls createOneWedge twice to make two adjacent wedges
    #because a wedge between those two degree measures may cause the resulting
    #clip/erase triangle to be too large for the input projection.  As an
    #extreme case, a 180-degree wedge would result in the creation of an invalid
    #clip/erase triangle, while a 179.999 degree wedge, for example, could
    #result in the creation of an extremely wide clip/erase triangle, one that
    #ArcGIS may not be able to work with.  After creating the two adjacent
    #wedges, the tool then merges and dissolves them to make the full wedge.
    #Once the wedge is made, it checks whether the optional inner radius
    #parameter is present in the wedge list.  If it is, it creates a circle of
    #that inner radius and uses it to erase from the wedge, resulting in the
    #final "arcband."

    Keyword arguments:
    attributesList -- A list of lists.  Each list contains 5 or 6 entries:
        -- The number of the wedge, used to join the output wedges back up
        with the input point feature class's attribute table (int)
        -- The X coordinate of the center of the wedge (int or float)
        -- The Y coordinate of the center of the wedge (int or float)
        -- The start line of bearing of the wedge (int or float)
        -- The end line of bearing of the wedge (int or float)
        -- The outer radius of the wedge (int or float)
        -- The inner radius of the wedge (optional) (int or float)
    inputFC -- The path to the tool's input point feature class (string)
    outputFC -- The path to the tool's output point feature class (string)
    outProj -- The projection of the output point feature class
    (arcpy.SpatialReference)
    """

    try:

        #Keep track of how many wedges have been processed
        count = 1

        #Build a list of strings containing the paths to the individual wedge
        #feature classes that are being made so that they can all be combined
        #into one final output feature class at the end
        mergeList = []

        #Process each wedge in turn
        for wedge in attributesList:

            #Extract the mandatory information about the wedge from its list
            wedgeNumber = wedge[0]
            centerX = wedge[1]
            centerY = wedge[2]
            angleA = wedge[3]
            angleB = wedge[4]
            r1 = wedge[5]

            #If the user enters two lines of bearing that are identical, skip
            #that wedge entirely, but if the user enters two lines of bearing
            #that differ by a multiple of 360 degrees, make a complete circle,
            #instead.  Check whether the user wants a complete circle out of the
            #current wedge before we start doing math on the lines of bearing.
            booFullCircle = False

            if (angleB - angleA) % 360 == 0:
                if angleB != angleA:
                    booFullCircle = True

            #Reduce the angles to a range between 0 (inclusive) and 360
            #(exclusive)
            angleA = angleA % 360
            angleB = angleB % 360

            #Calculate the difference between the two angles
            theta = (angleB - angleA) % 360

            #If theta = 0 and the user didn't want a full circle to be created
            #then there is no wedge to be created at all, so just skip it
            #completely, but keep track of the count variable for later table
            #joining purposes, and let the user know that we've skipped a
            #wedge.
            if theta == 0 and booFullCircle == False:
                printMessage("Skipping wedge " + str(count) + \
                             " (0-degree wedge)...")
                count += 1

            #If theta is too close to 180 degrees, the triangle math may fail
            #because the coordinates of the Clip/Erase triangle will become
            #extremely large in magnitude.  In those cases, make two smaller
            #wedges and dissolve them together.
            else:
                printMessage("Creating wedge " + str(count) + " of " + \
                             str(len(attributesList))+ "...")
                if 135 < (theta % 360) < 225:

                    #Create the first wedge
                    angleB = (angleA + theta/2) % 360
                    wedge1 = createOneWedge(centerX, centerY, r1, angleA,
                                            angleB, "WedgeA", outProj)

                    #Create the second wedge
                    angleA = angleB
                    angleB = (angleB + theta/2) % 360
                    wedge2 = createOneWedge(centerX, centerY, r1, angleA,
                                            angleB, "WedgeB", outProj)

                    #Now merge the two wedges, dissolve, and clean up
                    arcpy.Merge_management([wedge1, wedge2],
                                           "in_memory\\WedgeC")
                    arcpy.Delete_management("in_memory\\WedgeA")
                    arcpy.Delete_management("in_memory\\WedgeB")

                    oWedge = "in_memory\\oWedge"
                    arcpy.Dissolve_management("in_memory\\WedgeC", oWedge)
                    arcpy.Delete_management("in_memory\\WedgeC")
                   
                    del wedge1
                    del wedge2
                    
                #If theta is not between 135 and 225 degrees, proceed normally
                else:
                    oWedge = createOneWedge(centerX, centerY, r1, angleA,
                                            angleB, "oWedge", outProj)

                #If there's a second radius field, use it to trim down the
                #current wedge.  The wedge[6] checks are because if the user
                #created the radius2 field in a shapefile and didn't fill it for
                #some or all of the wedges, the field will still be present with
                #a single space in it.  If that's the case, just ignore the
                #radius2 field for that particular feature.
                if len(wedge) == 7 and wedge[6] != None and wedge[6] != '' \
                   and wedge[6] != ' ':
                    oWedge = innerWedgeErase(centerX, centerY, wedge[6], oWedge,
                                             outProj)

                #Now update the new wedge feature class's Id field to keep
                #count.  This will be used later for the table join with the
                #input shapefile.
                arcpy.AddField_management(oWedge, "Id", 'LONG')

                rows = arcpy.da.UpdateCursor(oWedge, "Id")

                for row in rows:
                    row[0] = wedgeNumber
                    rows.updateRow(row)
                del rows
                count += 1

                #Give the new wedge a unique name in the in_memory workspace and
                #add it to the list of wedge feature classes to be merged
                #together at the end
                nextWedge = "in_memory\\nextWedge" + str(count)
                arcpy.CopyFeatures_management(oWedge, nextWedge)
                arcpy.Delete_management(oWedge)
                mergeList.append(nextWedge)
                del oWedge
                del nextWedge

        #Now merge the individual wedge shapefiles into the final feature class
        printMessage('Merging wedges...')
        arcpy.Merge_management(mergeList, outputFC)

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))


def processWedges():

    """Process the inputs and create the output wedge feature class."""

    #Allow ArcGIS geoprocesses to overwrite outputs
    arcpy.env.overwriteOutput = True

    try:
        #Input feature class
        inputFC = arcpy.GetParameter(0)
        #Field containing first lines of bearing
        fieldFirstBearing = arcpy.GetParameterAsText(1)
        #Field containing second lines of bearing
        fieldSecondBearing = arcpy.GetParameterAsText(2)
        #Field containing outer wedge/arcband radius length
        fieldOuterRadius = arcpy.GetParameterAsText(3)
        #Field containing inner wedge/arcband radius length (if present)
        fieldInnerRadius = arcpy.GetParameterAsText(4)
        #Output wedge/arcband feature class
        outputFC = arcpy.GetParameterAsText(5)

        #Due to the nature of the calculations the tool performs, it should not
        #be run on WGS84 data or data with no projection information.
        desc = arcpy.Describe(inputFC)
        if desc.spatialReference.Name == "Unknown":
            printMessage("ERROR: Input shapefile does not have projection " + \
                         "information.",2)
            return
        elif desc.spatialReference.Name == "GCS_WGS_1984":
            printMessage("ERROR: Please reproject shapefile to a non-WGS84 " + \
                         "projection.",2)
            return
        elif desc.spatialReference.linearUnitName == "Degree":
            printMessage("ERROR: Please reproject shapefile from " + \
                         "geographic coordinates.",2)
            return

        #Counter variable to let the user know about bad input rows
        count = 1

        #Use the same spatial reference as the input feature class
        outProj = desc.spatialReference

        #Check whether the input is a layer from an active ArcMap session or a
        #feature class from disk.  The input has been grabbed as an object
        #instead of as text.  Try the dataSource method.  If the input is a
        #layer, we'll get the layer's path on disk and proceed.  If it's a
        #feature class, the dataSource method will fail, but then we know it's a
        #feature class, and the except block will just grab the input as text
        #because it will have the feature class's path.  In either case, we can
        #proceed.
        try:
            inputFC = inputFC.dataSource
        except:
            inputFC = arcpy.GetParameterAsText(0)

        #Check whether the input fields are ok.  Start by assuming that every
        #required field (or optional field, in the case of "radius2") is
        #missing until proven otherwise.
        gotAngleA  = False
        gotAngleB  = False
        gotRadius  = False
        gotRadius2 = False

        #Get the input fields from the input shapefile
        fieldList = arcpy.ListFields(inputFC)

        for field in fieldList:
            if field.name == fieldFirstBearing:
                #Don't accept the first bearing field if it's not of a numeric
                #type
                if field.type not in ['SmallInteger','Integer','Single',
                                      'Double','Float']:
                    printMessage('Error: Input feature class field ' + \
                                 field.name + ' is not a numeric field.',2)
                    return
                angle1FieldName = field.name
                gotAngleA = True

            elif field.name == fieldSecondBearing:
                #Don't accept the second bearing field if it's not of a numeric
                #type
                if field.type not in ['SmallInteger','Integer','Single',
                                      'Double','Float']:
                    printMessage('Error: Input feature class field ' + \
                                 field.name + ' is not a numeric field.',2)
                    return
                angle2FieldName = field.name
                gotAngleB = True

            elif field.name == fieldOuterRadius:
                #Don't accept the outer radius field if it's not of text type
                if field.type not in ['String']:
                    printMessage('Error: Input feature class field ' + \
                                 field.name + ' is not a text field.',2)
                    return
                r1FieldName = field.name
                gotRadius = True

            #The inner radius field isn't strictly necessary, but we need to
            #know if the field is present because if it is, we have to verify
            #that its values are valid for input
            elif field.name == fieldInnerRadius:

                #Don't accept the inner radius field if it's not of text type
                if field.type not in ['String']:
                    printMessage('Error: Input shapefile field ' + \
                                 field.name + ' is not a text field.',2)
                    return
                r2FieldName = field.name
                gotRadius2 = True

        if gotAngleA == False:
            printMessage('ERROR: Input shapefile does not have field for ' + \
                         'first line of bearing.',2)
            return

        elif gotAngleB == False:
            printMessage('ERROR: Input shapefile does not have field for ' + \
                         'second line of bearing.',2)
            return
                                      
        elif gotRadius == False:
            printMessage('ERROR: Input shapefile does not have field for ' + \
                         'radius.',2)
            return

        #Attributes in attributeList are stored in this order: centerX, centerY,
        #angleA, angleB, r1, wedgeNumber, r2 (optional).  Check for formatting
        #errors in the radius field(s) before proceeding.

        #Lists to hold all of the wedge/arcband attributes
        attributesList = []

        if gotRadius2:
            rows = arcpy.da.SearchCursor(inputFC, ["OID@", "SHAPE@XY",
                                                   angle1FieldName,
                                                   angle2FieldName, r1FieldName,
                                                   r2FieldName])
        else:
            rows = arcpy.da.SearchCursor(inputFC, ["OID@", "SHAPE@XY",
                                                   angle1FieldName,
                                                   angle2FieldName,
                                                   r1FieldName])

        for row in rows:
            #List to hold the attributes of one wedge/arcband
            oneAttributeSetList = []

            #Grab the feature ID, X coordinate, Y coordinate, and two lines of
            #bearing
            oneAttributeSetList.append(row[0])
            oneAttributeSetList.append(row[1][0])
            oneAttributeSetList.append(row[1][1])
            oneAttributeSetList.append(row[2])
            oneAttributeSetList.append(row[3])

            #Grab the radius and parse it to return the distance in meters
            r1 = parseRadius(row[4], desc.spatialReference.linearUnitName)

            #Make sure the radius field is formatted properly
            if r1 == None:
                printMessage('ERROR: Input formatting error in ' + \
                             fieldOuterRadius + ' field, feature ' + str(count) + ".",2)
                return
            oneAttributeSetList.append(r1)

            #Make sure the radius2 field is formatted properly if present.  If
            #it is properly formatted, add it to the current wedge/arcband's
            #attribute list.
            if gotRadius2 == True:
                if row[5] in ['',' ']:
                    r2 = ''
                else:
                    r2 = parseRadius(row[5],
                                     desc.spatialReference.linearUnitName)
                if r2 == None:
                    printMessage('ERROR: Input formatting error in ' + \
                                 fieldInnerRadius + ' field, feature ' + \
                                 str(count) + ".",2)
                    return
                oneAttributeSetList.append(r2)

            #Add the attributes from one wedge to attributesList
            attributesList.append(oneAttributeSetList)

            #Increment the counter
            count += 1

        del row
        del rows

        #Create the wedges.  The output will be a feature class in the output
        #location called outputFC.
        createWedges(attributesList, inputFC, outputFC, outProj)

        #Join the original attribute table to the new wedge shapefile
        #attribute table.        
        printMessage('Joining table...')

        #skipFieldList holds all the fields we don't want to join to the new
        #feature class.  It includes "Shape" as well as the OID field name.
        skipFieldList = ['Shape', arcpy.Describe(inputFC).OIDFieldName]

        #Build a list of fields to join
        joinFieldsList = []

        for field in fieldList:
            if field.name not in skipFieldList:
                joinFieldsList.append(field.name)

        #Build the parameter for the JoinField_management tool
        joinFieldsParameter = ";".join(joinFieldsList)

        arcpy.JoinField_management(outputFC, "Id", inputFC,
                                   arcpy.Describe(inputFC).OIDFieldName,
                                   joinFieldsParameter)

        #We don't need the new "Id_1" or "ORIG_FID" fields
        arcpy.DeleteField_management(outputFC, "Id_1")
        arcpy.DeleteField_management(outputFC, "ORIG_FID")

    except Exception as e:
        tb = sys.exc_info()[2]
        arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
        print str(e)
        arcpy.AddError(str(e))

################################################################################

try:
    #Check that the appropriate license level is available to the user
    if arcpy.CheckProduct("arcinfo") != "AlreadyInitialized":
        printMessage("ERROR: The required ArcGIS for Desktop Advanced " + \
                     "license is unavailable.", 2)
    else:
        processWedges()

except Exception as e:
    tb = sys.exc_info()[2]
    arcpy.AddError("An error occured on line %i" % tb.tb_lineno)
    print str(e)
    arcpy.AddError(str(e))
