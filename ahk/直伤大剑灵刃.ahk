#NoEnv
#NoTrayIcon
#SingleInstance
SetKeyDelay, -1
Gui +OwnDialogs
GuiControlGet, kai, , startfont
ScriptDir := A_ScriptDir
NewFolder := ScriptDir . "\config"
FileCreateDir, %NewFolder%
IniFilePath := ScriptDir . "\config\成小林直伤灵刃.ini"
IniWrite, "free", %iniFilePath%, "本脚本免费使用", by:
wpcolor:="wpcolor"
keys := ["wp1","wp2", "wp3","wp4", "wp5"]
for index, key in keys {
	IniRead, %key%x, %iniFilePath%, %wpcolor%, %key%x
	IniRead, %key%y, %iniFilePath%, %wpcolor%, %key%y
	IniRead, %key%color, %iniFilePath%, %wpcolor%, %key%color
}
twpcolor:="twpcolor"
keys := ["twp2","twp3","twp4","twp5"]
for index, key in keys {
	IniRead, %key%x, %iniFilePath%, %twpcolor%, %key%x
	IniRead, %key%y, %iniFilePath%, %twpcolor%, %key%y
	IniRead, %key%color, %iniFilePath%, %twpcolor%, %key%color
}
tycolor:="tycolor"
keys := ["ty1", "ty2", "ty3", "ty4", "ty5"]
for index, key in keys {
	IniRead, %key%x, %iniFilePath%, %tycolor%, %key%x
	IniRead, %key%y, %iniFilePath%, %tycolor%, %key%y
	IniRead, %key%color, %iniFilePath%, %tycolor%, %key%color
}
fcolor:="fcolor"
keys := ["f1", "f2", "f3", "f4", "f5","point","point2"]
for index, key in keys {
	IniRead, %key%x, %iniFilePath%, %fcolor%, %key%x
	IniRead, %key%y, %iniFilePath%, %fcolor%, %key%y
	IniRead, %key%color, %iniFilePath%, %fcolor%, %key%color
}
Hotkeys:="Hotkeys"
keys := ["wp1key", "wp2key", "wp3key", "wp4key", "wp5key", "ty1key", "ty2key", "ty3key", "ty4key", "ty5key", "f1key", "f2key", "f3key", "f4key", "f5key", "qwqkey", "startkey", "savecolorkey", "savekey","alltime"]
defaultValues := ["1", "2", "3", "4", "5", "z", "x", "c", "v", "tab", "F1", "F2", "F3", "F4", "F5", "``", "xbutton2", "f9", "f10","12"]
for index, key in keys {
	IniRead, %key%, %iniFilePath%, %Hotkeys%, %key%
	if (%key% = "" or %key% = "error") {
		%key% := defaultValues[index]
	}
}
qwq:="qwq"
IniRead, qwqx, %iniFilePath%, %qwq%, qwqx
IniRead, qwqy, %iniFilePath%, %qwq%, qwqy
IniRead, qwqcolor, %iniFilePath%, %qwq%, qwqcolor
IniRead, startfont, %iniFilePath%, %Hotkeys%, startfont
if(startfont="" or startfont= "error")
{
	startfont:= "启动中"
}
mieshi:="mieshi"
IniRead, mieshix, %iniFilePath%, %mieshi%, mieshix
IniRead, mieshiy, %iniFilePath%, %mieshi%, mieshiy
IniRead, mieshicolor, %iniFilePath%, %mieshi%, mieshicolor
IniRead, startfont, %iniFilePath%, %Hotkeys%, startfont
if(startfont="" or startfont= "error")
{
	startfont:= "启动中"
}
Label=%1%
if (Label!="")
{
	Suspend, On
	if IsLabel(Label)
		Gosub  %Label%
	ExitApp
}
Menu, Tray, Icon
Class Thread
{
	__New(Label)
	{
		if (A_IsCompiled)
			Run, "%A_ScriptFullPath%" /f "%Label%",,, pid
		else
			Run, "%A_AhkPath%" /f "%A_ScriptFullPath%" "%Label%",,, pid
		this.pid:=pid
	}
	__Delete()
	{
		Process, Close, % this.pid
	}
}
Hotkey, %startkey%, startrun
Hotkey, %savecolorkey%, findcolor
Hotkey, %savekey%, savekey
return
startrun:
	xPos := qwqx-20
    yPos := qwqy-30
    SplashImage,, X%xPos% Y%yPos% H22 W60 fs8 CW00FF00 CT000000 ZX2 ZY5 B8, %startfont%

	aaa1 := (onoff1 := !onoff1) ? new Thread("a1") : ""
	if(startkey =="capslock" )
	{
		if( onoff1 = 0)
		{
			SetCapsLockState, Off
			SplashImage, Off
		}
	}
	if(startkey !="capslock" )
	{
		if( onoff1 = 0)
		{
			SplashImage, Off
		}
	}
return
a1:
	a:= 0
	b:= 0
	c:= 0
	d:= 0
	global lastKeyTime := A_TickCount
	global lastKeyTime2 := A_TickCount
	getty4:=GetPixelColor(ty4x,ty4y)
	if(getty4==ty4color)
	{
		SendLoop(ty4key,1620)
	}
	getqwq:=GetPixelColor(qwqx,qwqy)
	gettwp2:=GetPixelColor(twp2x,twp2y)
	gettwp3:=GetPixelColor(twp3x,twp3y)
	gettwp4:=GetPixelColor(twp4x,twp4y)
	gettwp5:=GetPixelColor(twp5x,twp5y)
	if ((gettwp5==twp5color|| gettwp4==twp4color || gettwp3==twp3color || gettwp2==twp2color) && getqwq==qwqcolor)
	{
		Gosub  a4
	}
	getwp2:=GetPixelColor(wp2x,wp2y)
	getwp3:=GetPixelColor(wp3x,wp3y)
	getwp4:=GetPixelColor(wp4x,wp4y)
	getwp5:=GetPixelColor(wp5x,wp5y)
	if (getwp5==wp5color|| getwp4==wp4color || getwp3==wp3color || getwp2==wp2color)
	{
		Gosub  b3
	}
	getqwq:=GetPixelColor(qwqx,qwqy)
	gettwp2:=GetPixelColor(twp2x,twp2y)
	gettwp3:=GetPixelColor(twp3x,twp3y)
	gettwp4:=GetPixelColor(twp4x,twp4y)
	gettwp5:=GetPixelColor(twp5x,twp5y)
	if ((gettwp5==twp5color|| gettwp4==twp4color || gettwp3==twp3color || gettwp2==twp2color) && getqwq!=qwqcolor)
	{
		Gosub  b2
	}
a4:
	Loop
	{
		getty2:=GetPixelColor(ty2x,ty2y)
		if (getty2==ty2color)
		{
			loop 10
			{
				SendLoop(ty2key,75)
			}
		}
		gettwp3:=GetPixelColor(twp3x,twp3y)
		if (gettwp3==twp3color)
		{
			loop 10
			{
				SendLoop(wp3key,35)
			}
		}
		gettwp5:=GetPixelColor(twp5x,twp5y)
		if (gettwp5==twp5color)
		{
			getf5:=GetPixelColor(f5x,f5y)
			if (getf5==f5color)
			{
				SendLoop(f5key,1)
			}
			loop 10
			{
				SendLoop(wp5key,70)
			}
			a:=a+1
		}
		gettwp2:=GetPixelColor(twp2x,twp2y)
		if (gettwp2==twp2color)
		{
			loop 10
			{
				SendLoop(wp2key,81)
			}
		}
		getqwq:=GetPixelColor(qwqx,qwqy)
		if (getqwq==qwqcolor && a>0)
		{
			loop 10
			{
				SendLoop(qwqkey,23)
			}
			loop 10
			{
				SendLoop(wp4key,69)
			}
			getwp4:=GetPixelColor(wp4x,wp4y)
			if (getwp4!="0x000000")
			{
				loop
				{
					getwp4:=GetPixelColor(wp4x,wp4y)
					if (getwp4!="0x000000")
					{
						SendLoop(wp4key,10)
					}
					else
					{
						break
					}
				}
				getty5:=GetPixelColor(ty5x,ty5y)
				if (getty5==ty5color)
				{
					SendLoop(ty5key,1)
				}
				getty1:=GetPixelColor(ty1x,ty1y)
				if (getty1==ty1color)
				{
					loop 10
					{
						SendLoop(ty1key,85)
					}
					loop 10
					{
						SendLoop(wp4key,62)
					}
					getwp4:=GetPixelColor(wp4x,wp4y)
					if (getwp4!="0x000000")
					{
						loop
						{
							getwp4:=GetPixelColor(wp4x,wp4y)
							if (getwp4!="0x000000")
							{
								SendLoop(wp4key,10)
							}
							else
							{
								break
							}
						}
					}
				}
			}
			getty1:=GetPixelColor(ty1x,ty1y)
			getwp4:=GetPixelColor(wp4x,wp4y)
			if (getty1==ty1color && getwp4=="0x000000")
			{
				loop 10
				{
					SendLoop(ty1key,92)
				}
				getty5:=GetPixelColor(ty5x,ty5y)
				if (getty5==ty5color)
				{
					SendLoop(ty5key,1)
				}
				loop 10
				{
					SendLoop(wp4key,62)
				}
			}
			getpoint2:=GetPixelColor(point2x,point2y)
			 
			if(getpoint2==point2color)
			{
				SendLoop(ty4key,1)
			}
			getwp3:=GetPixelColor(wp3x,wp3y)
			if (getwp3==wp3color )
			{
				loop 10
				{
					SendLoop(wp3key,29)
				}
			}
			getwp2:=GetPixelColor(wp2x,wp2y)
			if (getwp2==wp2color)
			{
				loop 10
				{
					SendLoop(wp2key,75)
				}
			}
			getpoint:=GetPixelColor(pointx,pointy)
			getf1:=GetPixelColor(f1x,f1y)
			if (getf1==f1color && getpoint==pointcolor)
			{
				loop 10
				{
					SendLoop(f1key,64)
				}
			}
			getty3:=GetPixelColor(ty3x,ty3y)
			if (getty3==ty3color)
			{
				loop 10
				{
					SendLoop(ty3key,68)
				}
			}
			getty2:=GetPixelColor(ty2x,ty2y)
			if (getty2==ty2color)
			{
				loop 10
				{
					SendLoop(ty2key,75)
				}
			}
			a:= 0
			b:= 0
			Gosub  b1
		}
		Else
		{
			send 1
			sleep 1
		}
	}
return
b1:
	a:= 0
	b:= 0
	Loop
	{
		gettwp2:=GetPixelColor(twp2x,twp2y)
		gettwp3:=GetPixelColor(twp3x,twp3y)
		gettwp4:=GetPixelColor(twp4x,twp4y)
		gettwp5:=GetPixelColor(twp5x,twp5y)
		if (gettwp5==twp5color|| gettwp4==twp4color || gettwp3==twp3color || gettwp2==twp2color)
		{
			Gosub  b2
		}
		getwp4:=GetPixelColor(wp4x,wp4y)
		if (getwp4==wp4color)
		{
			{
				loop 10
				{
					SendLoop(wp4key,59)
				}
				c:=c+1
			}
			getwp2:=GetPixelColor(wp2x,wp2y)
			if (getwp2==wp2color)
			{
				loop 10
				{
					SendLoop(wp2key,77)
				}
				d:=d+1
			}
		}
		getpoint2:=GetPixelColor(point2x,point2y)
		 
		if(getpoint2==point2color)
		{
			SendLoop(ty4key,1)
		}
		getwp3:=GetPixelColor(wp3x,wp3y)
		if (getwp3==wp3color)
		{
			loop 10
			{
				SendLoop(wp3key,29)
			}
			getf3:=GetPixelColor(f3x,f3y)
			if (getf3==f3color)
			{
				loop 10
				{
					SendLoop(f3key,45)
				}
			}
		}
		getwp2:=GetPixelColor(wp2x,wp2y)
		if (getwp2==wp2color)
		{
			loop 10
			{
				SendLoop(wp2key,79)
			}
			d:=d+1
		}
		getpoint:=GetPixelColor(pointx,pointy)
		getf1:=GetPixelColor(f1x,f1y)
		if (getf1==f1color && getpoint==pointcolor)
		{
			loop 10
			{
				SendLoop(f1key,64)
			}
		}
		getf1:=GetPixelColor(f1x,f1y)
		getf2:=GetPixelColor(f2x,f2y)
		getpoint:=GetPixelColor(pointx,pointy)
		if (getf2==f2color && getf1=="0x000000" && getpoint==pointcolor)
		{
			loop 10
			{
				SendLoop(f2key,50)
			}
		}
		getqwq:=GetPixelColor(qwqx,qwqy)
		if (getqwq==qwqcolor && c>0 && d>=2)
		{
			loop 10
			{
				SendLoop(qwqkey,23)
			}
			lastKeyTime := A_TickCount
			loop 10
			{
				SendLoop(wp5key,75)
			}
			loop 10
			{
				SendLoop(wp2key,50)
			}
			loop 10
			{
				SendLoop(wp3key,45)
			}
			loop 10
			{
				SendLoop(wp1key,100)
			}
			getpoint:=GetPixelColor(pointx,pointy)
			getf1:=GetPixelColor(f1x,f1y)
			if (getf1==f1color && getpoint==pointcolor)
			{
				loop 10
				{
					SendLoop(f1key,76)
				}
			}
			Gosub  b2
		}
		getty3:=GetPixelColor(ty3x,ty3y)
		if (getty3==ty3color)
		{
			loop 10
			{
				SendLoop(ty3key,68)
			}
		}
		getty2:=GetPixelColor(ty2x,ty2y)
		if (getty2==ty2color)
		{
			loop 10
			{
				SendLoop(ty2key,75)
			}
		}
		Else
		{
			SendLoop(wp1key,1)
		}
	}
return
b2:
	c:= 0
	d:= 0
	Loop
	{
		getwp2:=GetPixelColor(wp2x,wp2y)
		getwp3:=GetPixelColor(wp3x,wp3y)
		getwp4:=GetPixelColor(wp4x,wp4y)
		getwp5:=GetPixelColor(wp5x,wp5y)
		if (getwp5==wp5color|| getwp4==wp4color || getwp3==wp3color || getwp2==wp2color)
		{
			Gosub  b1
		}
		getpoint:=GetPixelColor(pointx,pointy)
		getf1:=GetPixelColor(f1x,f1y)
		if (getf1==f1color && getpoint==pointcolor)
		{
			loop 10
			{
				SendLoop(f1key,64)
			}
		}
		getqwq:=GetPixelColor(qwqx,qwqy)
		getty2:=GetPixelColor(ty2x,ty2y)
		if (getty2==ty2color && (A_TickCount - lastKeyTime >= 9457))
		{
			loop 10
			{
				SendLoop(ty2key,75)
			}
			gettwp2:=GetPixelColor(twp2x,twp2y)
			if (gettwp2==twp2color)
			{
				loop 10
				{
					SendLoop(wp2key,43)
				}
			}
		}
		gettwp2:=GetPixelColor(twp2x,twp2y)
		if (gettwp2==twp2color)
		{
			loop 10
			{
				SendLoop(wp2key,43)
			}
		}
		gettwp5:=GetPixelColor(twp5x,twp5y)
		if (gettwp5==twp5color)
		{
			getf5:=GetPixelColor(f5x,f5y)
			if (getf5==f5color)
			{
				SendLoop(f5key,1)
			}
			loop 10
			{
				SendLoop(wp5key,100)
			}
			a:=a+1
		}
		gettwp3:=GetPixelColor(twp3x,twp3y)
		if (gettwp3==twp3color)
		{
			loop 10
			{
				SendLoop(wp3key,44)
			}
			loop 10
			{
				SendLoop(wp1key,2)
			}
			b:=b+1
		}
		getqwq:=GetPixelColor(qwqx,qwqy)
		if (getqwq==qwqcolor && a>0 && b>0)
		{
			loop 10
			{
				SendLoop(qwqkey,23)
			}
			loop 10
			{
				SendLoop(wp4key,69)
			}
			getwp4:=GetPixelColor(wp4x,wp4y)
			if (getwp4!="0x000000")
			{
				loop
				{
					getwp4:=GetPixelColor(wp4x,wp4y)
					if (getwp4!="0x000000")
					{
						SendLoop(wp4key,10)
					}
					else
					{
						break
					}
				}
				getty5:=GetPixelColor(ty5x,ty5y)
				if (getty5==ty5color)
				{
					SendLoop(ty5key,1)
				}
				getty1:=GetPixelColor(ty1x,ty1y)
				if (getty1==ty1color)
				{
					loop 10
					{
						SendLoop(ty1key,80)
					}
					loop 10
					{
						SendLoop(wp4key,62)
					}
					getwp4:=GetPixelColor(wp4x,wp4y)
					if (getwp4!="0x000000")
					{
						loop
						{
							getwp4:=GetPixelColor(wp4x,wp4y)
							if (getwp4!="0x000000")
							{
								SendLoop(wp4key,10)
							}
							else
							{
								break
							}
						}
					}
				}
			}
			getty1:=GetPixelColor(ty1x,ty1y)
			getwp4:=GetPixelColor(wp4x,wp4y)
			if (getty1==ty1color && getwp4=="0x000000")
			{
				loop 10
				{
					SendLoop(ty1key,92)
				}
				SendLoop(ty5key,1)
				loop 10
				{
					SendLoop(wp4key,80)
				}
			}
			getpoint2:=GetPixelColor(point2x,point2y)
			 
			if(getpoint2==point2color)
			{
				SendLoop(ty4key,1)
			}
			getwp3:=GetPixelColor(wp3x,wp3y)
			if (getwp3==wp3color )
			{
				loop 10
				{
					SendLoop(wp3key,29)
				}
			}
			getwp2:=GetPixelColor(wp2x,wp2y)
			if (getwp2==wp2color)
			{
				loop 10
				{
					SendLoop(wp2key,75)
				}
			}
			getf1:=GetPixelColor(f1x,f1y)
			if (getf1==f1color)
			{
				loop 10
				{
					SendLoop(f1key,64)
				}
			}
			getty3:=GetPixelColor(ty3x,ty3y)
			if (getty3==ty3color)
			{
				loop 10
				{
					SendLoop(ty3key,68)
				}
			}
			getty2:=GetPixelColor(ty2x,ty2y)
			if (getty2==ty2color)
			{
				loop 10
				{
					SendLoop(ty2key,75)
				}
			}
			Gosub  b1
		}
		getpoint2:=GetPixelColor(point2x,point2y)
		 
		if(getpoint2==point2color)
		{
			SendLoop(ty4key,1)
		}
		Else
		{
			SendLoop(wp1key,1)
		}
	}
return
b3:
	c:= 0
	d:= 0
	Loop
	{
		gettwp2:=GetPixelColor(twp2x,twp2y)
		gettwp3:=GetPixelColor(twp3x,twp3y)
		gettwp4:=GetPixelColor(twp4x,twp4y)
		gettwp5:=GetPixelColor(twp5x,twp5y)
		if (gettwp5==twp5color|| gettwp4==twp4color || gettwp3==twp3color || gettwp2==twp2color)
		{
			Gosub  b2
		}
		getwp4:=GetPixelColor(wp4x,wp4y)
		if (getwp4==wp4color)
		{
			loop
			{
				getwp4:=GetPixelColor(wp4x,wp4y)
				if (getwp4!="0x000000")
				{
					SendLoop(wp4key,10)
				}
				else
				{
					break
				}
			}
		}
		getwp3:=GetPixelColor(wp3x,wp3y)
		if (getwp3==wp3color)
		{
			loop 10
			{
				SendLoop(wp3key,29)
			}
			getf3:=GetPixelColor(f3x,f3y)
			if (getf3==f3color)
			{
				loop 10
				{
					SendLoop(f3key,45)
				}
			}
		}
		getpoint2:=GetPixelColor(point2x,point2y)
		 
		if(getpoint2==point2color)
		{
			SendLoop(ty4key,1)
		}
		getwp2:=GetPixelColor(wp2x,wp2y)
		if (getwp2==wp2color)
		{
			loop 10
			{
				SendLoop(wp2key,75)
			}
		}
		getqwq:=GetPixelColor(qwqx,qwqy)
		if (getqwq==qwqcolor && (A_TickCount - lastKeyTime2 >= 4012))
		{
			loop 10
			{
				SendLoop(qwqkey,23)
			}
			lastKeyTime := A_TickCount
			loop 10
			{
				SendLoop(wp5key,75)
			}
			loop 10
			{
				SendLoop(wp2key,50)
			}
			loop 10
			{
				SendLoop(wp3key,45)
			}
			loop 10
			{
				SendLoop(wp1key,160)
			}
			getpoint:=GetPixelColor(pointx,pointy)
			getf1:=GetPixelColor(f1x,f1y)
			if (getf1==f1color && getpoint==pointcolor)
			{
				loop 10
				{
					SendLoop(f1key,76)
				}
			}
			Gosub  b2
		}
		getty3:=GetPixelColor(ty3x,ty3y)
		if (getty3==ty3color)
		{
			loop 10
			{
				SendLoop(ty3key,68)
			}
		}
		getty2:=GetPixelColor(ty2x,ty2y)
		if (getty2==ty2color)
		{
			loop 10
			{
				SendLoop(ty2key,75)
			}
		}
		Else
		{
			SendLoop(wp1key,1)
		}
	}
return
a2:
	loop
	{
		getpoint:=GetPixelColor(pointx,pointy)
		if(getpoint==pointcolor)
		{
			getf1:=GetPixelColor(f1x,f1y)
			if(getf1==f1color)
			{
				loop
				{
					SendLoop(f1key, 10)
					getpoint:=GetPixelColor(pointx,pointy)
					if(getpoint!=pointcolor)
					{
						break
					}
				}
			}
		}
	}
return
findcolor:
	sltime:=100
	jumptime:=100
	msgbox "下面将开始对武器技能取色"`n"请按照文字提示依次移动到技能左上角11点方向，按下" %savecolorkey%
	saveType := "wpcolor"
	wp := ["2", "3", "4", "5"]
	Loop, % wp.MaxIndex()
	{
		skill := wp[A_Index]
		Loop
		{
			tooltip "请移动到大剑技能" %skill% "，11点方向按下"%savecolorkey%
			if GetKeyState(savecolorkey, "P")
			{
				MouseGetPos, xpos, ypos
				mousemove, xpos, ypos - 200
				sleep %sltime%
				PixelGetColor, color, %xpos%, %ypos%, RGB
				IniWrite, %xpos%, %iniFilePath%, %saveType%, wp%skill%x
				IniWrite, %ypos%, %iniFilePath%, %saveType%, wp%skill%y
				IniWrite, %color%, %iniFilePath%, %saveType%, wp%skill%color
				mousemove, xpos, ypos
				tooltip "获取完毕"
				sleep jumptime
				tooltip
				break
			}
			if GetKeyState("ESC", "P")
			{
				tooltip "跳过"
				sleep jumptime
				tooltip
				break
			}
		}
	}
	keys := ["wp1","wp2", "wp3","wp4", "wp5"]
	for index, key in keys {
		IniRead, %key%x, %iniFilePath%, wpcolor, %key%x
		IniRead, %key%y, %iniFilePath%, wpcolor, %key%y
		IniRead, %key%color, %iniFilePath%, wpcolor, %key%color
	}
	getwp2:=GetPixelColor(wp2x,wp2y)
	getwp3:=GetPixelColor(wp3x,wp3y)
	getwp4:=GetPixelColor(wp4x,wp4y)
	getwp5:=GetPixelColor(wp5x,wp5y)
	msgbox "匕聚检测"`n"武器2颜色" %getwp2% "武器2本地颜色" %wp2color%`n"武器3颜色" %getwp3% "武器3本地颜色" %wp3color%`n"武器4颜色" %getwp4% "武器4本地颜色" %wp4color%`n"武器5颜色" %getwp5% "武器5本地颜色" %wp5color%`n
	saveType := "twpcolor"
	twp := ["2", "3", "4", "5"]
	Loop, % wp.MaxIndex()
	{
		skill := twp[A_Index]
		Loop
		{
			tooltip "请移动到匕剑技能" %skill% "，11点方向按下"%savecolorkey%
			if GetKeyState(savecolorkey, "P")
			{
				MouseGetPos, xpos, ypos
				mousemove, xpos, ypos - 200
				sleep %sltime%
				PixelGetColor, color, %xpos%, %ypos%, RGB
				IniWrite, %xpos%, %iniFilePath%, %saveType%, twp%skill%x
				IniWrite, %ypos%, %iniFilePath%, %saveType%, twp%skill%y
				IniWrite, %color%, %iniFilePath%, %saveType%, twp%skill%color
				mousemove, xpos, ypos
				tooltip "剑/匕技能" %skill% "获取完毕"
				sleep jumptime
				tooltip
				break
			}
			if GetKeyState("ESC", "P")
			{
				tooltip "跳过"
				sleep jumptime
				tooltip
				break
			}
		}
	}
	keys := ["twp2","twp3","twp4","twp5"]
	for index, key in keys {
		IniRead, %key%x, %iniFilePath%, twpcolor, %key%x
		IniRead, %key%y, %iniFilePath%, twpcolor, %key%y
		IniRead, %key%color, %iniFilePath%, twpcolor, %key%color
	}
	gettwp2:=GetPixelColor(twp2x,twp2y)
	gettwp3:=GetPixelColor(twp3x,twp3y)
	gettwp4:=GetPixelColor(twp4x,twp4y)
	gettwp5:=GetPixelColor(twp5x,twp5y)
	msgbox "匕聚检测"`n"武器2颜色" %gettwp2% "武器2本地颜色" %twp2color%`n"武器3颜色" %gettwp3% "武器3本地颜色" %twp3color%`n"武器4颜色" %gettwp4% "武器4本地颜色" %twp4color%`n"武器5颜色" %gettwp5% "武器5本地颜色" %twp5color%`n
	saveType := "tycolor"
	ty:= ["1","2", "3", "4", "5"]
	Loop, % ty.MaxIndex()
	{
		skill := ty[A_Index]
		Loop
		{
			if(skill==1)
			{
				tooltip "移动到通用1（幻光纹章）11点处按下F9"
			}
			if(skill==2)
			{
				tooltip "移动到通用2（幻影除魔）11点处按下F9"
			}
			if(skill==3)
			{
				tooltip "移动到通用3（剑刃暴雨）11点处按下F9"
			}
			if(skill==4)
			{
				tooltip "移动到通用4（苦痛咒语）11点处按下F9"
			}
			if(skill==5)
			{
				tooltip "移动到通用5（千刀万剐）11点处按下F9"
			}
			if GetKeyState(savecolorkey, "P")
			{
				MouseGetPos, xpos, ypos
				mousemove,xpos,ypos-200
				sleep %sltime%
				PixelGetColor, color, %xpos%, %ypos%, RGB
				IniWrite, %xpos%, %iniFilePath%, %saveType%, ty%skill%x
				IniWrite, %ypos%, %iniFilePath%, %saveType%, ty%skill%y
				IniWrite, %color%, %iniFilePath%, %saveType%, ty%skill%color
				mousemove, xpos, ypos
				tooltip "通用技能" %skill% "获取完毕"
				sleep jumptime
				tooltip
				break
			}
			if GetKeyState("ESC", "P")
			{
				tooltip "跳过"
				sleep jumptime
				tooltip
				break
			}
		}
	}
	keys := ["ty1", "ty2", "ty3", "ty4", "ty5"]
	for index, key in keys {
		IniRead, %key%x, %iniFilePath%, tycolor, %key%x
		IniRead, %key%y, %iniFilePath%, tycolor, %key%y
		IniRead, %key%color, %iniFilePath%, tycolor, %key%color
	}
	getty1:=GetPixelColor(ty1x,ty1y)
	getty2:=GetPixelColor(ty2x,ty2y)
	getty3:=GetPixelColor(ty3x,ty3y)
	getty4:=GetPixelColor(ty4x,ty4y)
	msgbox "通用颜色检测"`n"通用1颜色" %getty1% "副武器1本地颜色" %ty1color%`n"通用2颜色" %getty2% "通用2本地颜色" %ty2color%`n"通用3颜色" %getty3% "通用3本地颜色" %ty3color%`n"通用4颜色" %getty4% "通用4本地颜色" %ty4color%`n
	saveType := "fcolor"
	f:= ["1","2", "3", "4", "5"]
	Loop, % f.MaxIndex()
	{
		skill := f[A_Index]
		Loop
		{
			tooltip "请移动到F1-F5技能" F%skill% "，11点方向按下"%savecolorkey%
			if GetKeyState(savecolorkey, "P")
			{
				MouseGetPos, xpos, ypos
				mousemove,xpos,ypos-200
				sleep %sltime%
				PixelGetColor, color, %xpos%, %ypos%, RGB
				IniWrite, %xpos%, %iniFilePath%, %saveType%, f%skill%x
				IniWrite, %ypos%, %iniFilePath%, %saveType%, f%skill%y
				IniWrite, %color%, %iniFilePath%, %saveType%, f%skill%color
				mousemove, xpos, ypos
				tooltip "F1-F5技能" F%skill% "获取完毕"
				sleep jumptime
				tooltip
				break
			}
			if GetKeyState("ESC", "P")
			{
				tooltip "跳过"
				sleep jumptime
				tooltip
				break
			}
		}
	}
	loop
	{
		tooltip "请在满豆子状态下，移动到第五个豆子中心处"
		if GetKeyState(savecolorkey, "P")
		{
			saveType := "fcolor"
			MouseGetPos, xpos, ypos
			mousemove,xpos,ypos-200
			sleep %sltime%
			PixelGetColor, color, %xpos%, %ypos%, RGB
			IniWrite, %xpos%, %iniFilePath%, %saveType%, pointx
			IniWrite, %ypos%, %iniFilePath%, %saveType%, pointy
			IniWrite, %color%, %iniFilePath%, %saveType%, pointcolor
			mousemove, xpos, ypos
			tooltip "豆子取色完毕"
			sleep jumptime
			tooltip
			break
		}
		if GetKeyState("ESC", "P")
		{
			tooltip "跳过"
			sleep jumptime
			tooltip
			break
		}
	}
	loop
	{
		tooltip "苦痛咒语打开后强力钉刺数字2下面一横最左边白色部分（建议用截屏模式取色）"
		if GetKeyState(savecolorkey, "P")
		{
			saveType := "fcolor"
			MouseGetPos, xpos, ypos
			mousemove,xpos,ypos-200
			sleep %sltime%
			PixelGetColor, color, %xpos%, %ypos%, RGB
			IniWrite, %xpos%, %iniFilePath%, %saveType%, point2x
			IniWrite, %ypos%, %iniFilePath%, %saveType%, point2y
			IniWrite, %color%, %iniFilePath%, %saveType%, point2color
			mousemove, xpos, ypos
			tooltip "幻象2位置"
			sleep jumptime
			tooltip
			break
		}
		if GetKeyState("ESC", "P")
		{
			tooltip "跳过"
			sleep jumptime
			tooltip
			break
		}
	}
	loop
	{
		tooltip "请移动到切武器图标箭头处按下"%savecolorkey%
		if GetKeyState(savecolorkey, "P")
		{
			saveType := "qwq"
			MouseGetPos, xpos, ypos
			mousemove,xpos,ypos-200
			sleep %sltime%
			PixelGetColor, color, %xpos%, %ypos%, RGB
			IniWrite, %xpos%, %iniFilePath%, %saveType%, qwqx
			IniWrite, %ypos%, %iniFilePath%, %saveType%, qwqy
			IniWrite, %color%, %iniFilePath%, %saveType%, qwqcolor
			mousemove, xpos, ypos
			msgbox "切武器获取完毕"
			sleep jumptime
			tooltip
			break
		}
		if GetKeyState("ESC", "P")
		{
			tooltip "跳过"
			sleep jumptime
			tooltip
			break
		}
	}
	loop
	{
		tooltip "请移动到蔑视条处按下"%savecolorkey%
		if GetKeyState(savecolorkey, "P")
		{
			saveType := "mieshi"
			MouseGetPos, xpos, ypos
			mousemove,xpos,ypos-200
			sleep %sltime%
			PixelGetColor, color, %xpos%, %ypos%, RGB
			IniWrite, %xpos%, %iniFilePath%, %saveType%, mieshix
			IniWrite, %ypos%, %iniFilePath%, %saveType%, mieshiy
			IniWrite, %color%, %iniFilePath%, %saveType%, mieshicolor
			mousemove, xpos, ypos
			msgbox "蔑视条获取完毕,可开启热键循环"
			sleep jumptime
			tooltip
			break
		}
		if GetKeyState("ESC", "P")
		{
			tooltip "跳过"
			sleep jumptime
			tooltip
			break
		}
	}
return
savekey:
	IfWinExist, MyGui
	{
		WinActivate, MyGui
	}
	{
		Gui, MyGui: New , 0 , 热键
		Gui Add, Text, x10 y10 w50 h20, 武器
		Gui Add, Hotkey, x10 y30 w50 vwp1key Choose, %wp1key%
		Gui Add, Hotkey, x10 y60 w50 vwp2key Choose, %wp2key%
		Gui Add, Hotkey, x10 y90 w50 vwp3key Choose, %wp3key%
		Gui Add, Hotkey, x10 y120 w50 vwp4key Choose, %wp4key%
		Gui Add, Hotkey, x10 y150 w50 vwp5key Choose, %wp5key%
		Gui Add, Text, x80 y10 w50 h20, 通用
		Gui Add, Hotkey, x70 y30 w70 vty1key Choose, %ty1key%
		Gui Add, Hotkey, x70 y60 w70 vty2key Choose, %ty2key%
		Gui Add, Hotkey, x70 y90 w70 vty3key Choose, %ty3key%
		Gui Add, Hotkey, x70 y120 w70 vty4key Choose, %ty4key%
		Gui Add, Hotkey, x70 y150 w70 vty5key Choose, %ty5key%
		Gui Add, Text, x140 y10 w50 h20, F1-F5
		Gui Add, Hotkey, x150 y30 w70 vf1key Choose, %f1key%
		Gui Add, Hotkey, x150 y60 w70 vf2key Choose, %f2key%
		Gui Add, Hotkey, x150 y90 w70 vf3key Choose, %f3key%
		Gui Add, Hotkey, x150 y120 w70 vf4key Choose, %f4key%
		Gui Add, Hotkey, x150 y150 w70 vf5key Choose, %f5key%
		Gui Add, Text, x10 y185 w50 h20, 切
		Gui Add, edit, x30 y180 w70 vqwqkey Choose, %qwqkey%
		Gui Add, Text, x110 y185 w50 h20, 启
		Gui Add, edit, x130 y180 w70 vstartkey Choose, %startkey%
		Gui Add, Text, x10 y210 w50 h20, 取
		Gui Add, Hotkey, x30 y210 w70 vsavecolorkey Choose, %savecolorkey%
		Gui Add, Text, x110 y210 w50 h20, 存
		Gui Add, Hotkey, x130 y210 w70 vsavekey Choose, %savekey%
		Gui Add, Text, x10 y240 w50 h20, 开
		Gui, Add, Edit,x30 y240 w70 vstartfont ,%startfont%
		Gui Add, Text, x110 y240 w50 h20, 全局延迟
		Gui Add, edit, x165 y240 w30 valltime , %alltime%
		Gui Add, Button, x90 y270 w50 h30 gSaveButton default, 保存
		Gui Show
	}
return
SaveButton:
	gui Submit
	saveType := "Hotkeys"
	IniWrite, %wp1key%, %iniFilePath%, %saveType%, wp1key
	IniWrite, %wp2key%, %iniFilePath%, %saveType%, wp2key
	IniWrite, %wp3key%, %iniFilePath%, %saveType%, wp3key
	IniWrite, %wp4key%, %iniFilePath%, %saveType%, wp4key
	IniWrite, %wp5key%, %iniFilePath%, %saveType%, wp5key
	IniWrite, %ty1key%, %iniFilePath%, %saveType%, ty1key
	IniWrite, %ty2key%, %iniFilePath%, %saveType%, ty2key
	IniWrite, %ty3key%, %iniFilePath%, %saveType%, ty3key
	IniWrite, %ty4key%, %iniFilePath%, %saveType%, ty4key
	IniWrite, %ty5key%, %iniFilePath%, %saveType%, ty5key
	IniWrite, %f1key%, %iniFilePath%, %saveType%, f1key
	IniWrite, %f2key%, %iniFilePath%, %saveType%, f2key
	IniWrite, %f3key%, %iniFilePath%, %saveType%, f3key
	IniWrite, %f4key%, %iniFilePath%, %saveType%, f4key
	IniWrite, %f5key%, %iniFilePath%, %saveType%, f5key
	IniWrite, %qwqkey%, %iniFilePath%, %saveType%, qwqkey
	IniWrite, %startkey%, %iniFilePath%, %saveType%, startkey
	IniWrite, %savecolorkey%, %iniFilePath%, %saveType%, savecolorkey
	IniWrite, %savekey%, %iniFilePath%, %saveType%, savekey
	IniWrite, %kai%, %iniFilePath%, %saveType%, startfont
	IniWrite, %alltime%, %iniFilePath%,sleep, alltime
	MsgBox, 保存成功！
return
GetPixelColor(x,y)
{
	PixelGetColor, color, x, y, RGB
	return color
}
SendLoop(key, loopCount) {
	global alltime
	patternHotkey := "F[1-9]|F1[0-2]"
	patternShift := "shift"
	patternmbutton := "mbutton"
	patternmtab := "tab"
	isHotkey := RegExMatch(key, patternHotkey)
	isShift := RegExMatch(key, patternShift)
	isMbutton := RegExMatch(key, patternmbutton)
	istab := RegExMatch(key, patternmtab)
	if (isHotkey || isShift || isMbutton ||istab) {
		send, {%key%}
	} else {
		send, %key%
	}
	sleep, (loopCount-alltime)
}