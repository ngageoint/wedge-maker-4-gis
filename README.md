##About

The Wedge Maker for ArcGIS is an ArcGIS tool that allows the user to create wedge and arcband (a wedge with a part of the cone of the wedge erased) shapes.

###Usage

The user chooses one of the two tools within the ArcGIS toolbox.  The different tools allow the user to specify either the two lines of bearing or the line of bearing and swath that will help define each wedge/arcband.  After opening either tool in ArcGIS, the user specifies the following:

*The input point feature class
*The names of the fields that specify either the two lines of bearing or the bearing and swath that define the angular extent of the wedges.
*The name of the field that contains the outer radius of each wedge.
*Optionally, the name of the field that contains the inner radius of each arcband.
*The output polygon feature class.

The entries in the radius field(s) must be in the format required by ESRI's ArcGIS Buffer tool.  For example, "5 MILES", "3.41 kilometers", or "23 NauticalMiles".  The units must be specified.  If the user provides an inner radius field, then input rows that contain an entry in that field will be made into an arcband shape by creating the full wedge shape and then erasing from the center of the wedge outward by the distance specified in the inner radius field.  If the user provides an inner radius field, the user may still leave some entries in the inner radius field blank, in which case a full wedge will be created for that row.

###Methodology (summary)

For each input point, the tool reads the point's coordinates and attributes.  The tool buffers the point by the outer radius distance, and then calculates the vertices of a triangle that can be used to clip or erase from the buffer in order to leave the desired wedge shape.  Then, if the user wanted an arcband shape, the tool buffers the point again by the inner radius distance and then erases from the wedge shape with the buffer.  Finally, the tool combines all of the output wedge/arcband shapes into a single polygon feature class and uses the Join Field tool to join the input point feature class's attribute table to the output polygon feature class's attribute table.

####Methodology (in-depth)



###Notes

Because the tool performs distance calculations, the tool requires that the input point feature class be projected.  The tool attempts to detect if the user provides unprojected data (such as WGS84 lat-long data) and halts operations if it detects unprojected data.  If the tool fails to detect the unprojected data, it will still run by the output wedge/arcband shapes cannot be considered reliable.

The tool considers due North to be 0 degrees bearing and bearing increases in a clockwise direction.  The tool allows input lines of bearing less than 0 degrees and greater than 360 degrees.  If the user provides an identical line of bearing for both the start and end of a wedge shape (or provides a swath width of 0 degrees), the tool interprets this as a 0-degree wedge and skips its creation altogether.  If the user provides two lines of bearing that differ by a multiple of 360 degrees but not 0, then the tool interprets this as a 360-degree wedge.  For example, two input lines of bearing of "120" would result in no wedge being created, but input lines of bearing of "120" and "-240" would result in a full circle shape being created.  If the difference in input lines of bearing is greater than 360 degrees, then the tool will reduce the difference by 360 degrees repeatedly until both lines of bearing are between 0 and 360 degrees.  For example, input lines of bearing of "120" and "540" are equivalent to input lines of bearing of "120" and "180".

###Origin

Wedge Maker was developed at the National Geospatial-Intelligence Agency (NGA) by a federal government employee in the course of their employment, so it is not subject to copyright protection and is in the public domain.

###Pull Requests

If you'd like to contribute to this project, please make a pull request. We'll review the pull request and discuss the changes. This project is in the public domain within the United States and all changes to the core public domain portions will be released back into the public domain. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest. Modifications to dependencies under copyright-based open source licenses are subject to the original license conditions.
